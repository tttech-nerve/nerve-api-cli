# Copyright (c) 2026 TTTech Industrial Automation AG.
#
# ALL RIGHTS RESERVED.
# Usage of this software, including source code, netlists, documentation,
# is subject to restrictions and conditions of the applicable license
# agreement with TTTech Industrial Automation AG or its affiliates.
#
# All trademarks used are the property of their respective owners.
#
# TTTech Industrial Automation AG and its affiliates do not assume any liability
# arising out of the application or use of any product described or shown
# herein. TTTech Industrial Automation AG and its affiliates reserve the right to
# make changes, at any time, in order to improve reliability, function or
# design.
#
# Contact Information:
# support@tttech-industrial.com
# TTTech Industrial Automation AG, Schoenbrunnerstrasse 7, 1040 Vienna, Austria


"""Function for backup and restore docker volumes using localui"""

import logging
import os
import re
import time

import requests
from nerve_lib import CheckStatusCodeError
from nerve_lib import DockerVolumes

from .utils import ask_for_confirmation
from .utils import file_read
from .utils import file_write
from .utils import format_size_string
from .utils import size_string_to_bytes


def args_docker_volumes_filter(parser):
    filter_arg = parser.add_argument_group("Filter arguments for volumes")
    filter_arg.add_argument(
        "--include-unnamed-volumes",
        action="store_true",
        help="Include auto-generated volumes in list, backup, restore, and prune operations",
    )
    filter_arg.add_argument(
        "--filter-name",
        default="",
        help=(
            "Include only volumes containing NAME string. Supports regex (prefix with "
            "'regex:'; e.g., 'regex:^db_')"
        ),
    )

    filter_arg.add_argument(
        "--filter-size",
        default="",
        help="Filter volumes by size: use '<500MB' or '>2GB'. Units: B, KB, MB, GB, TB",
    )


def args_docker_volumes(parser):
    # mandatory args

    args_docker_volumes_filter(parser)

    required_group = parser.add_argument_group("Mutually exclusive arguments for docker volumes")
    action_args = required_group.add_mutually_exclusive_group(required=False)
    action_args.add_argument(
        "--backup",
        action="store_true",
        help="Trigger Docker volume backup creation on nodes (Management System connection only)",
    )
    action_args.add_argument(
        "--download-backup",
        metavar="PATH",
        help="Download Docker volume backups from nodes to WORK_DIR/PATH/NODE_SERIAL/",
    )
    action_args.add_argument(
        "--restore",
        metavar="PATH",
        help="Restore Docker volumes on nodes from backups in WORK_DIR/PATH/NODE_SERIAL/",
    )
    action_args.add_argument(
        "--prune-docker-volumes",
        action="store_true",
        help="Remove all unused Docker volumes on nodes (volumes not used by any workload)",
    )


def filter_unnamed_volumes(volumes, log):
    filtered_volumes = []
    for volume in volumes:
        name = volume.get("name")
        if len(name) == 64 and all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in name):  # noqa: PLR2004
            log.debug("- %s: skipped (likely a unnamed volume created by a workload)", name)
            continue
        filtered_volumes.append(volume)
    return filtered_volumes


def get_filtered_volumes(serial_numbers, volumes_handle, args, log):

    filtered_volumes_all = {}
    for serial_number in serial_numbers:
        add_args = {"dut_serial": serial_number} if isinstance(volumes_handle, DockerVolumes) else {}
        volumes = volumes_handle.get_volumes(**add_args).get("volumes", [])
        filtered_volumes = []

        if not args.include_unnamed_volumes:
            filtered_volumes = filter_unnamed_volumes(volumes, log)
        else:
            filtered_volumes = volumes

        if args.filter_name:
            filter_str = args.filter_name
            if filter_str.startswith("regex:"):
                regex_pattern = filter_str[len("regex:") :]
                filtered_volumes = [
                    v for v in filtered_volumes if re.search(regex_pattern, v.get("name", ""))
                ]
            else:
                filtered_volumes = [v for v in filtered_volumes if filter_str in v.get("name", "")]

        if args.filter_size:
            size_filter = args.filter_size
            operator = None
            if size_filter.startswith(">"):
                operator = ">"
                size_threshold = size_string_to_bytes(size_filter[1:])
            elif size_filter.startswith("<"):
                operator = "<"
                size_threshold = size_string_to_bytes(size_filter[1:])
            else:
                raise ValueError(
                    "Invalid format for --filter-size. Expected format is '>500MB' or '<2GB'. Skipping size filter."
                )

            if operator and size_threshold is not None:
                if operator == ">":
                    filtered_volumes = [v for v in filtered_volumes if int(v.get("size", 0)) > size_threshold]
                elif operator == "<":
                    filtered_volumes = [v for v in filtered_volumes if int(v.get("size", 0)) < size_threshold]

        filtered_volumes_all[serial_number] = filtered_volumes

    return filtered_volumes_all


def sort_volumes_per_workload(volumes_info, log: logging.Logger | None = None):
    volume_info_dict = {}
    for serial_number, volumes in volumes_info.items():
        used_by_group = {}
        for volume in volumes:
            for workload in volume.get("usedByWorkloads", []):
                wl_version = f"{workload.get('name')}/{workload.get('versionName')}"
                if wl_version not in used_by_group:
                    used_by_group[wl_version] = []
                used_by_group[wl_version].append(volume)
            if not volume.get("usedByWorkloads", []):
                if "" not in used_by_group:
                    used_by_group[""] = []
                used_by_group[""].append(volume)

        volume_info_dict[serial_number] = used_by_group

    if log:
        for serial_number, used_by in volume_info_dict.items():
            log.info("Node '%s':", serial_number)
            for wl_version, vols in used_by.items():
                group_name = wl_version if wl_version else "unused"
                log.info("- Current Volumes used by '%s':", group_name)
                for vol in vols:
                    if vol.get("backupInfo"):
                        backup_exports = "; ".join(
                            f"{info.get('action')}->{info.get('status')} '{info.get('backupName')}'"
                            for info in vol["backupInfo"]
                        )
                    else:
                        backup_exports = ""
                    log.info(
                        "  - %s (%s)   %s",
                        vol["name"],
                        format_size_string(vol["size"], fraction_digits=0),
                        backup_exports,
                    )

    return volume_info_dict


def wait_for_import_completed(serial_numbers, volumes_handle, args, log, check_interval=30):
    filtered_volumes = get_filtered_volumes(serial_numbers, volumes_handle, args, log)
    for serial_number, volumes in filtered_volumes.items():
        for volume in volumes:
            import_backup_info = [
                info for info in volume.get("backupInfo", []) if info.get("action") == "import"
            ]
            in_progress_imports = [info for info in import_backup_info if info.get("status") != "COMPLETED"]
            failed_imports = [info for info in import_backup_info if info.get("status") == "FAILED"]
            if failed_imports:
                raise ValueError(
                    f"Import of volume '{volume.get('name')}' on node '{serial_number}'"
                    " failed with status 'FAILED' in MS after restore operation. Please check the MS for details."
                )
            if in_progress_imports:
                log.info(
                    "Waiting for import of volume '%s' on node '%s' to be completed. Current status: %s",
                    volume.get("name"),
                    serial_number,
                    in_progress_imports[0].get("status"),
                )
                time.sleep(check_interval)
                wait_for_import_completed(
                    [serial_number], volumes_handle, args, log, check_interval=check_interval
                )


def docker_volumes(serial_numbers, args, volumes_handle, log):  # noqa: PLR0912, PLR0914, PLR0915
    ret_val = 0

    if args.backup and not isinstance(volumes_handle, DockerVolumes):
        raise ValueError(
            "The --backup option is only applicable when using MS connection."
            " Local UI allows to download the backup directly using --download-backup PATH option."
        )

    filtered_volumes = get_filtered_volumes(serial_numbers, volumes_handle, args, log)

    # Print the filtered volumes per node and workload
    used_by_group = sort_volumes_per_workload(filtered_volumes, log=log)

    if args.backup:
        perform_action = ask_for_confirmation(
            args,
            "Are you sure you want to trigger a docker volumes backup?",
        )
        for serial_number, volumes in filtered_volumes.items():
            for volume in volumes:
                name = volume.get("name")
                size = int(volume.get("size"))
                if not perform_action:
                    log.info(
                        "Skipping backup of volume '%s' (%s) on node '%s'",
                        name,
                        format_size_string(size, fraction_digits=0),
                        serial_number,
                    )
                    continue
                try:
                    volumes_handle.export_volume_data_ms(
                        dut_serial=serial_number, volume_name=name, export_timeout=300000
                    )
                    log.info(
                        "Triggered backup of volume '%s' (%s): successful",
                        name,
                        format_size_string(size, fraction_digits=0),
                    )
                except CheckStatusCodeError as ex_msg:
                    if (
                        ex_msg.status_code == requests.codes.not_found
                        and "Docker volume mount point is empty." in ex_msg.value
                    ):
                        log.debug(
                            "Triggered backup of volume '%s' (%s): empty volume, skipping",
                            name,
                            format_size_string(size, fraction_digits=0),
                        )
                    else:
                        log.error(
                            "Triggered backup of volume '%s' (%s): failed (%s)",
                            name,
                            format_size_string(size, fraction_digits=0),
                            ex_msg,
                        )
                        ret_val = 2

    if args.download_backup:  # noqa: PLR1702
        ret_val = 0
        open_volumes_list = filtered_volumes.copy()
        finished_volumes = {serial_number: [] for serial_number in serial_numbers}
        perform_action = ask_for_confirmation(
            args, "Are you sure you want to download the backup of the docker volumes? "
        )
        while any(volumes for volumes in open_volumes_list.values()):
            for serial_number, volumes in open_volumes_list.items():
                add_args = {"dut_serial": serial_number} if isinstance(volumes_handle, DockerVolumes) else {}
                node_vol_dump_path = os.path.join(args.work_dir, args.download_backup, serial_number)
                os.makedirs(node_vol_dump_path, exist_ok=True)
                file_write(
                    node_vol_dump_path,
                    "volumes.json",
                    {"volumes": volumes},
                )
                for volume in volumes:
                    if isinstance(
                        volumes_handle, DockerVolumes
                    ):  # MS backup download (after triggering backup)
                        backup_info = [
                            info for info in volume.get("backupInfo", []) if info.get("action") == "export"
                        ]
                        if not backup_info:
                            if (
                                volume.get("size") == 4096  # noqa: PLR2004
                            ):  # volume is empty (default size for empty volumes), skipping with debug log
                                log.debug(
                                    "Volume '%s' does not have backup information available but is empty. Skipping download of this volume.",
                                    volume.get("name"),
                                )
                            else:
                                log.warning(
                                    (
                                        "Volume '%s' '%d' does not have backup information available. Trigger the backup upfront with --backup."
                                        " Skipping download of this volume."
                                    ),
                                    volume.get("name"),
                                    volume.get("size"),
                                )
                                ret_val = 1
                            finished_volumes[serial_number].append(volume)
                            continue
                        for info in backup_info:
                            if info.get("status") == "COMPLETED":
                                backup_name = info.get("backupName")
                                if not perform_action:
                                    log.info(
                                        "Skipping download of backup '%s' for volume '%s' on node '%s'",
                                        backup_name,
                                        volume.get("name"),
                                        serial_number,
                                    )
                                    finished_volumes[serial_number].append(volume)
                                    continue
                                try:  # noqa: PLW0717
                                    log.info(
                                        "Downloading backup '%s' for volume '%s' ... ",
                                        backup_name,
                                        volume.get("name"),
                                    )
                                    time_download_start = time.time()
                                    data = volumes_handle.ms.get(
                                        f"/nerve_node/storage/docker-volume-backups-export/{serial_number}/{backup_name}",
                                        accepted_status=[requests.codes.ok],
                                        stream=True,
                                        timeout=300000,
                                    )
                                    try:
                                        file_path = os.path.join(node_vol_dump_path, backup_name)
                                        with open(file_path, "wb") as export_file:
                                            export_file.writelines(
                                                chunk for chunk in data.iter_content(chunk_size=8192)
                                            )
                                    finally:
                                        close_data = getattr(data, "close", None)
                                        if callable(close_data):
                                            close_data()
                                    log.info(
                                        "   ... successful. Downloaded in %d seconds (%.2f Mb/s)",
                                        time.time() - time_download_start,
                                        int(volume.get("size", 0))
                                        / (1024 * 1024)
                                        / (time.time() - time_download_start),
                                    )
                                    finished_volumes[serial_number].append(volume)
                                except CheckStatusCodeError as ex_msg:
                                    log.error(
                                        "   ... failed with status code %s: %s",
                                        ex_msg.status_code,
                                        ex_msg.response_text,
                                    )
                                    ret_val = 2
                                except TimeoutError:
                                    log.error(
                                        "   ... failed with timeout after %d seconds",
                                        time.time() - time_download_start,
                                    )
                                    ret_val = 2
                            else:
                                log.info(
                                    "Backup '%s' for volume '%s' is not completed (current status: %s). Postponing download.",
                                    info.get("backupName"),
                                    volume.get("name"),
                                    info.get("status"),
                                )
                    else:  # LocalUI backup download
                        log.info(
                            "Backing up volume '%s' (%s) ... ",
                            volume["name"],
                            format_size_string(volume.get("size", 0), fraction_digits=0),
                        )
                        time_download_start = time.time()
                        if not perform_action:
                            log.info(
                                "Skipping backup of volume '%s' (%s) on node '%s'",
                                volume["name"],
                                format_size_string(volume.get("size", 0), fraction_digits=0),
                                serial_number,
                            )
                            finished_volumes[serial_number].append(volume)
                            continue
                        try:
                            volumes_handle.export_volume_data(
                                volume_name=volume["name"],
                                file_path=os.path.join(
                                    node_vol_dump_path,
                                    f"{volume['name']}-{int(time_download_start * 1000)}.zip",
                                ),
                                export_timeout=300000,
                            )
                            log.info(
                                "   ... successful. Downloaded in %d seconds (%.2f Mb/s)",
                                time.time() - time_download_start,
                                volume.get("size", 0) / (1024 * 1024) / (time.time() - time_download_start),
                            )
                            finished_volumes[serial_number].append(volume)
                        except CheckStatusCodeError as ex_msg:
                            if (
                                ex_msg.status_code == requests.codes.not_found
                                and "Docker volume mount point is empty." in ex_msg.value
                            ):
                                log.debug("   ... empty volume, skipping")
                            else:
                                log.error(
                                    "   ... failed with status code %s: %s",
                                    ex_msg.status_code,
                                    ex_msg.response_text,
                                )
                                ret_val = 2
                        except TimeoutError:
                            log.error(
                                "   ... failed with timeout after %d seconds",
                                time.time() - time_download_start,
                            )
                            ret_val = 2
            for serial_number, volumes in open_volumes_list.items():
                open_volumes_list[serial_number] = [
                    v for v in volumes if v not in finished_volumes[serial_number]
                ]
            if all(not volumes for volumes in open_volumes_list.values()):
                break

            log.info("Waiting 1 minute for remaining backups to be completed ...")
            time.sleep(60)

            # update volume information of open_volumes_list
            open_volumes_list = get_filtered_volumes([serial_number], volumes_handle, args, log)
            # remove finished volumes from open_volumes_list
            for serial_number, volumes in open_volumes_list.items():
                open_volumes_list[serial_number] = [
                    v for v in volumes if v not in finished_volumes[serial_number]
                ]

        return ret_val
    if args.restore:
        perform_action = ask_for_confirmation(
            args, "Are you sure you want to restore the docker volumes from backup?"
        )
        for serial_number, existing_volumes in used_by_group.items():
            node_vol_dump_path = os.path.join(args.work_dir, args.restore, serial_number)
            if not os.path.exists(node_vol_dump_path):
                raise RuntimeError(
                    "No backup found for node with serial number '%s' at path '%s'",
                    serial_number,
                    node_vol_dump_path,
                )

            # check if volumes are present on node before restoring
            backup_volumes = file_read(
                args.work_dir, os.path.join(args.restore, serial_number, "volumes.json")
            ).get("volumes", [])
            if not args.include_unnamed_volumes:
                backup_volumes = filter_unnamed_volumes(backup_volumes, log)

            backup_workload_volumes = sort_volumes_per_workload({serial_number: backup_volumes}).get(
                serial_number, {}
            )

            # remove unused volumes from existing and backup list for the check
            existing_volumes.pop("", None)  # existing volumes
            backup_workload_volumes.pop("", None)  # backup volumes

            if set(existing_volumes.keys()) < set(backup_workload_volumes.keys()):
                log.warning(
                    "The current volumes on the node do not match the backup. "
                    "Ensure that the node is in a similar state as when the backup was taken."
                )
                log.info(
                    "Current set of workload using volumes: %s", ", ".join(sorted(set(existing_volumes)))
                )
                log.info(
                    "Backup set of workload using volumes:  %s",
                    ", ".join(sorted(set(backup_workload_volumes))),
                )

                if ask_for_confirmation(
                    args,
                    "Do you want to proceed with the restore to matching volumes anyway? (yes/no): ",
                ):
                    log.info("Proceeding with restore operation despite the mismatch in volumes.")
                else:
                    raise RuntimeError("Aborting restore operation due to volume mismatch.")

            for volume in backup_volumes:
                available_files = os.listdir(node_vol_dump_path)
                # find latest backup file matching '<volume_name>_<timestamp>.zip'
                volume_backup_pattern = re.compile(rf"^{re.escape(volume.get('name', ''))}-[0-9]+\.zip$")
                sorted_by_time_files = sorted(
                    [f for f in available_files if volume_backup_pattern.fullmatch(f)],
                    key=lambda x: os.path.getmtime(os.path.join(node_vol_dump_path, x)),
                    reverse=True,
                )
                if not sorted_by_time_files:
                    log.debug(
                        "Volume '%s': backup file not found, skipping restore of this volume",
                        volume.get("name"),
                    )
                    continue
                file_path = os.path.join(node_vol_dump_path, sorted_by_time_files[0])
                time_start = time.time()
                if volume.get("name") not in [v["name"] for v in filtered_volumes[serial_number]]:
                    log.warning(
                        "Volume '%s' from backup is not present on the node. Skipping restore of this volume.",
                        volume.get("name"),
                    )
                    continue

                if not perform_action:
                    log.info("Restoring volume '%s' skipped", os.path.basename(file_path))
                    continue
                log.info("Restoring volume '%s' started ... ", os.path.basename(file_path))
                try:
                    add_args = (
                        {"dut_serial": serial_number} if isinstance(volumes_handle, DockerVolumes) else {}
                    )
                    volumes_handle.import_volume_data(
                        volume_name=volume.get("name"), file_path=file_path, import_timeout=300000, **add_args
                    )
                    log.info(
                        "   ... successful. Uploaded in %d seconds (%.2f Mb/s)",
                        time.time() - time_start,
                        os.path.getsize(file_path) / (1024 * 1024) / (time.time() - time_start),
                    )
                except CheckStatusCodeError as ex_msg:
                    log.error(
                        "   ... failed with status code %s: %s", ex_msg.status_code, ex_msg.response_text
                    )
                    ret_val = 2
                except TimeoutError:
                    log.error("   ... failed with timeout after %d seconds", time.time() - time_start)
                    ret_val = 2
            # check status when restoring over MS
            if isinstance(volumes_handle, DockerVolumes):
                wait_for_import_completed([serial_number], volumes_handle, args, log)

        return ret_val

    if args.prune_docker_volumes:
        perform_action = ask_for_confirmation(
            args, "Are you sure you want to remove all unused docker volumes on the nodes?"
        )
        ret_val = 0
        for serial_number, volumes in used_by_group.items():
            unused_volumes = volumes.get("", [])
            if not unused_volumes:
                log.info("No unused volumes found on the node with serial number '%s'.", serial_number)
                continue
            log.info(
                "Unused volumes found on the node with serial number '%s': %s",
                serial_number,
                ", ".join([v["name"] for v in unused_volumes]),
            )
            for volume in unused_volumes:
                name = volume.get("name")
                if not perform_action:
                    log.info("Skipping removal of unused volume '%s' on node '%s'", name, serial_number)
                    continue
                log.info("Removing unused volume '%s' ... ", name)
                try:
                    add_args = (
                        {"dut_serial": serial_number} if isinstance(volumes_handle, DockerVolumes) else {}
                    )
                    volumes_handle.delete_volume(volume_name=name, **add_args)
                    log.info("   ... successful.")
                except CheckStatusCodeError as ex_msg:
                    log.error(
                        "   ... failed with status code %s: %s", ex_msg.status_code, ex_msg.response_text
                    )
                    ret_val = 2
        return ret_val

    return ret_val
