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
from nerve_lib import LocalNode
from nerve_lib import NodeHandle
from nerve_lib.manage_volumes import LocalDockerVolumes

from .utils import args_interactive
from .utils import file_read
from .utils import file_write
from .utils import format_size_string
from .utils import size_string_to_bytes


def args_docker_volumes(parser):
    # mandatory args

    options_group = parser.add_argument_group(
        "Options arguments for filtering volumes and specifying connection details. Per default a localUI connection"
        "over the management port of the device is used. Allowed optional arguments"
    )
    options_group.add_argument(
        "--localui_password",
        default="",
        help="Password for logging into the local UI using default admin account",
    )

    options_group.add_argument(
        "--filter_only_named",
        action="store_true",
        help="Only include named volumes in the volumes operations. ",
    )

    options_group.add_argument(
        "--filter_name",
        default="",
        help=(
            "Only include volumes whose name contains the specified string in the volume list and backup/restore operations. "
            "Supports regex (define 'regex:' followed by the filter-string)"
        ),
    )

    options_group.add_argument(
        "--filter_size",
        default="",
        help=(
            "Define a size threashold with '<' or '>' to only include volumes "
            "smaller or larger than the specified size in the volume list and backup/restore operations. "
            "E.g., '>500MB' to only include volumes larger than 500MB. Supported size units are B, KB, MB, GB, TB."
        ),
    )

    options_group.add_argument(
        "--use_ms",
        action="store_true",
        help=(
            "Use MS connection to backup/restore volumes instead of local UI connection. "
            "This requires the MS credentials to be provided."
        ),
    )
    options_group.add_argument(
        "--ms_credentials",
        action="store_true",
        help=(
            "Use MS credentials for logging into the local UI. This is used in case the default local UI"
            " credentials are deactivated and the local UI login with MS credentials is allowed. "
        ),
    )

    options_group.add_argument(
        "--nodes_file",
        metavar="FILE_NAME",
        default="nodes.json",
        help="Specify the file name which is listing the nodes to operate on. Defaults to 'nodes.json' if omitted. '.json' is appended if not included.",
    )

    options_group.add_argument(
        "--ip_address",
        metavar="NODE_IP_ADDRESS",
        default="172.20.2.1:3333",
        help="IP address and port of the local UI to connect to (e.g., 172.20.2.1:3333)",
    )

    options_group.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help=(
            "Automatic yes to prompts (in case of mismatch between backup volumes and current volumes on node)"
            " Allows to resume the restore operation even if the check for matching volumes fails. Use with caution!"
            " Assume 'yes' as answer to all prompts and run non-interactively"
        ),
    )
    options_group.add_argument(
        "--batch",
        action="store_true",
        help=(
            "Batch mode for restore operation. In case of mismatch between backup volumes and current volumes on"
            " the restore operation an error will be returned, unless the --yes flag is included"
        ),
    )

    required_group = parser.add_argument_group("Mutually exclusive arguments for action")
    commands_args = required_group.add_mutually_exclusive_group(required=True)

    commands_args.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List all Docker volumes on the node",
    )

    commands_args.add_argument(
        "--backup",
        action="store_true",
        help=(
            "Backup the Docker volumes from the node to the local machine "
            "(stored to '<work_dir>/volumes_backup/<node_serial>/<volume_name>.tar')"
            "For exports over MS, the backup will be triggered and can be downloaded via"
            "--download_backup after the export is completed and the backup is available."
        ),
    )
    commands_args.add_argument(
        "--download_backup",
        action="store_true",
        help=("Download the exported Docker volume data from the MS to the local machine. "),
    )
    commands_args.add_argument(
        "--restore",
        action="store_true",
        help=(
            "Restore the Docker volumes on the node from the local backup "
            "(from '<work_dir>/volumes_backup/<node_serial>/<volume_name>.tar')"
        ),
    )
    commands_args.add_argument(
        "--prune",
        action="store_true",
        help="Remove all unused Docker volumes on the node (volumes that are not used by any workload)",
    )


def get_node_serial(node_handle):
    local_node = LocalNode(node_handle)
    cloud_config = local_node.get_configuration()
    return cloud_config.get("serialNumber", "unknown_serial")


def filter_volumes(volumes, args, log):
    filtered_volumes = []

    if args.filter_only_named:
        for volume in volumes:
            name = volume.get("name")
            if len(name) == 64 and all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in name):  # noqa: PLR2004
                log.debug("- %s: skipped (likely a unnamed volume created by a workload)", name)
                continue
            filtered_volumes.append(volume)
    else:
        filtered_volumes = volumes

    if args.filter_name:
        filter_str = args.filter_name
        if filter_str.startswith("regex:"):
            regex_pattern = filter_str[len("regex:") :]
            filtered_volumes = [v for v in filtered_volumes if re.search(regex_pattern, v.get("name", ""))]
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
                "Invalid format for --filter_size. Expected format is '>500MB' or '<2GB'. Skipping size filter."
            )

        if operator and size_threshold is not None:
            if operator == ">":
                filtered_volumes = [v for v in filtered_volumes if int(v.get("size", 0)) > size_threshold]
            elif operator == "<":
                filtered_volumes = [v for v in filtered_volumes if int(v.get("size", 0)) < size_threshold]

    return filtered_volumes


def sort_volumes_per_workload(volumes, log):
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

    return used_by_group


def _connect_to_node(args, log):
    user = args.ms_user if args.ms_credentials else "local@nerve.cloud"
    password = args.ms_password if args.ms_credentials else args.localui_password

    log.info(
        "Connecting to node at '%s' for managing workloads and docker volumes through local UI",
        args.ip_address,
    )
    ip_addr, port = args.ip_address.split(":")
    node_handle = NodeHandle(ip_addr, local_bind_port=int(port))
    try:
        node_handle.login(user=user, password=password)
    except CheckStatusCodeError as ex_msg:
        if (
            ex_msg.status_code == requests.codes.bad_request
            and "default_admin_account_is_deactivated_use_your_personal_credentials_to_log_in"
            in ex_msg.response_text
            and args.ms_user
            and args.ms_password
        ):
            log.info(
                "Using MS-credentials of user '%s' to log in to local UI since default localui credentials are deactivated",
                args.ms_user,
            )
            node_handle.login(user=args.ms_user, password=args.ms_password)
        else:
            raise
    return node_handle


def _handle_docker_volumes(serial_number, args, volumes_handle, log, ms_handle=None):  # noqa: PLR0912, PLR0914, PLR0915
    add_args = {}
    ret_val = 0
    if args.use_ms:
        add_args = {"dut_serial": serial_number}

    volumes = volumes_handle.get_volumes(**add_args)
    filtered_volumes = filter_volumes(volumes.get("volumes", []), args, log)

    if args.list:  # noqa: PLR1702
        used_by_group = sort_volumes_per_workload(filtered_volumes, log)

        log.info("List of volumes for '%s':", serial_number)
        for group, vols in used_by_group.items():
            log.info("- Volumes used by '%s':", group if group else "unused")
            for vol in vols:
                if vol.get("backupInfo"):
                    backup_exports = [
                        f"{info.get('action')}->{info.get('status')} '{info.get('backupName')}'"
                        for info in vol["backupInfo"]
                    ]
                    backup_export_available = "; ".join(backup_exports)
                    if all(info["status"] == "COMPLETED" for info in vol["backupInfo"]):
                        loglevel = logging.INFO
                    else:
                        loglevel = logging.WARNING
                        ret_val = 1
                else:
                    backup_export_available = ""
                    loglevel = logging.INFO
                log.log(
                    loglevel,
                    "  - %s (%s)   %s",
                    vol["name"],
                    format_size_string(vol["size"], fraction_digits=0),
                    backup_export_available,
                )

        file_write(
            args.work_dir,
            os.path.join("volumes_backup", serial_number, "volumes.json"),
            {"volumes": filtered_volumes},
        )

    elif args.backup:
        node_vol_dump_path = os.path.join(args.work_dir, "volumes_backup", serial_number)
        os.makedirs(node_vol_dump_path, exist_ok=True)

        file_write(
            args.work_dir,
            os.path.join("volumes_backup", serial_number, "volumes.json"),
            {"volumes": filtered_volumes},
        )
        for volume in filtered_volumes:
            name = volume.get("name")
            size = int(volume.get("size"))

            time_start = time.time()
            if not args.use_ms:
                log.info(
                    "Backing up volume '%s' (%s) ... ", name, format_size_string(size, fraction_digits=0)
                )
                try:
                    volumes_handle.export_volume_data(
                        volume_name=name,
                        file_path=os.path.join(node_vol_dump_path, f"{name}-{int(time_start * 1000)}.zip"),
                        export_timeout=300000,
                        **add_args,
                    )
                    log.info(
                        "   ... successful. Downloaded in %d seconds (%.2f Mb/s)",
                        time.time() - time_start,
                        size / (1024 * 1024) / (time.time() - time_start),
                    )
                except CheckStatusCodeError as ex_msg:
                    if (
                        ex_msg.status_code == requests.codes.not_found
                        and "Docker volume mount point is empty." in ex_msg.value
                    ):
                        log.info("   ... empty volume, skipping")
                    else:
                        log.error(
                            "   ... failed with status code %s: %s", ex_msg.status_code, ex_msg.response_text
                        )
                        ret_val = 2
                except TimeoutError:
                    log.error("   ... failed with timeout after %d seconds", time.time() - time_start)
                    ret_val = 2
            else:  # MS
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
                    log.error(
                        "Triggered backup of volume '%s' (%s): failed (%s)",
                        name,
                        format_size_string(size, fraction_digits=0),
                        ex_msg,
                    )
                    ret_val = 2
    elif args.restore:
        node_vol_dump_path = os.path.join(args.work_dir, "volumes_backup", serial_number)
        if not os.path.exists(node_vol_dump_path):
            raise RuntimeError(
                "No backup found for node with serial number '%s' at path '%s'",
                serial_number,
                node_vol_dump_path,
            )

        # check if volumes are present on node before restoring
        backup_volumes = file_read(
            args.work_dir, os.path.join("volumes_backup", serial_number, "volumes.json")
        ).get("volumes", [])
        if not args.filter_only_named:
            backup_volumes = filter_volumes(backup_volumes, args, log)

        existing_workload_volumes = sort_volumes_per_workload(filtered_volumes, log)
        backup_workload_volumes = sort_volumes_per_workload(backup_volumes, log)

        # remove unused volumes from existing and backup list for the check
        existing_workload_volumes.pop("", None)
        backup_workload_volumes.pop("", None)

        if set(existing_workload_volumes.keys()) < set(backup_workload_volumes.keys()):
            log.warning(
                "The current volumes on the node do not match the backup. "
                "Ensure that the node is in a similar state as when the backup was taken."
            )
            log.info("Current workload using volumes: %s", ", ".join(sorted(set(existing_workload_volumes))))
            log.info("Backup workload using volumes:  %s", ", ".join(sorted(set(backup_workload_volumes))))

            user_input = "yes" if args.yes else ""
            if not args.batch or not args.yes:
                user_input = input(
                    "Do you want to proceed with the restore to matching volumes anyway? (yes/no): "
                )
            if user_input.lower() in {"yes", "y"}:
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
                    "Volume '%s': backup file not found, skipping restore of this volume", volume.get("name")
                )
                continue
            file_path = os.path.join(node_vol_dump_path, sorted_by_time_files[0])
            time_start = time.time()
            if volume.get("name") not in [v["name"] for v in filtered_volumes]:
                log.warning(
                    "Volume '%s' from backup is not present on the node. Skipping restore of this volume.",
                    volume.get("name"),
                )
                continue
            log.info("Restoring volume '%s' started ... ", os.path.basename(file_path))
            try:
                volumes_handle.import_volume_data(
                    volume_name=volume.get("name"), file_path=file_path, import_timeout=300000, **add_args
                )
                log.info(
                    "   ... successful. Uploaded in %d seconds (%.2f Mb/s)",
                    time.time() - time_start,
                    os.path.getsize(file_path) / (1024 * 1024) / (time.time() - time_start),
                )
            except CheckStatusCodeError as ex_msg:
                log.error("   ... failed with status code %s: %s", ex_msg.status_code, ex_msg.response_text)
                ret_val = 2
            except TimeoutError:
                log.error("   ... failed with timeout after %d seconds", time.time() - time_start)
                ret_val = 2

    elif args.prune:
        used_by_group = sort_volumes_per_workload(filtered_volumes, log)
        unused_volumes = used_by_group.get("", [])
        if not unused_volumes:
            log.info("No unused volumes found on the node.")
            return 0
        log.info("Unused volumes found on the node: %s", ", ".join([v["name"] for v in unused_volumes]))
        for volume in unused_volumes:
            name = volume.get("name")
            log.info("Removing unused volume '%s' ... ", name)
            try:
                volumes_handle.delete_volume(volume_name=name, **add_args)
                log.info("   ... successful.")
            except CheckStatusCodeError as ex_msg:
                log.error("   ... failed with status code %s: %s", ex_msg.status_code, ex_msg.response_text)
                ret_val = 2

    elif args.download_backup:
        if not args.use_ms:
            raise RuntimeError(
                "The --download_backup option is only applicable when using MS connection. Please include the --use_ms flag."
            )
        node_vol_dump_path = os.path.join(args.work_dir, "volumes_backup", serial_number)
        for volume in filtered_volumes:
            if not volume.get("backupInfo"):
                log.warning(
                    "Volume '%s' does not have backup information available. Skipping download of this volume.",
                    volume.get("name"),
                )
                continue
            for info in volume["backupInfo"]:
                while True:
                    if info.get("action") == "export" and info.get("status") == "BACKUP_CREATION_IN_PROGRESS":
                        time.sleep(60)
                        log.info(
                            "Waiting for backup creation to complete for volume '%s' ...", volume.get("name")
                        )
                    else:
                        break
                if info.get("action") == "export" and info.get("status") == "COMPLETED":
                    backup_name = info.get("backupName")
                    try:
                        log.info(
                            "Downloading backup '%s' for volume '%s' ... ", backup_name, volume.get("name")
                        )
                        time_start = time.time()
                        data = ms_handle.get(
                            f"/nerve_node/storage/docker-volume-backups-export/{serial_number}/{backup_name}",
                            accepted_status=[requests.codes.ok],
                            stream=True,
                            timeout=300000,
                        )
                        file_path = os.path.join(node_vol_dump_path, backup_name)
                        with open(file_path, "wb") as export_file:
                            export_file.writelines(chunk for chunk in data.iter_content(chunk_size=8192))
                        log.info(
                            "   ... successful. Downloaded in %d seconds (%.2f Mb/s)",
                            time.time() - time_start,
                            int(volume.get("size", 0)) / (1024 * 1024) / (time.time() - time_start),
                        )
                    except CheckStatusCodeError as ex_msg:
                        log.error(
                            "   ... failed with status code %s: %s", ex_msg.status_code, ex_msg.response_text
                        )
                        ret_val = 2
                    except TimeoutError:
                        log.error("   ... failed with timeout after %d seconds", time.time() - time_start)
                        ret_val = 2
                else:
                    log.warning(
                        "Backup '%s' for volume '%s' is not completed (current status: %s). Skipping download of this backup.",
                        info.get("backupName"),
                        volume.get("name"),
                        info.get("status"),
                    )
                    ret_val = 1
    return ret_val


def docker_volumes(ms_handle, arg, log=None):
    ret_val = 0
    log = log.getChild(__name__.split(".")[-1]) if log else logging.getLogger(__name__)
    args = args_interactive(
        arg,
        add_args_function=args_docker_volumes,
        description="Docker Volumes management over local UI or MS.",
    )
    if not args:
        log.error("Failed to parse arguments")
        return 2

    if args.use_ms:
        log.info("Using MS connection to manage docker volumes on the node")
        ms_volumes = DockerVolumes(ms_handle)
        nodes = file_read(args.work_dir, args.nodes_file)
        for node in nodes:
            ret_val = max(
                _handle_docker_volumes(node["serialNumber"], args, ms_volumes, log, ms_handle), ret_val
            )

    else:
        node_handle = _connect_to_node(args, log)
        local_volumes = LocalDockerVolumes(node_handle)
        serial_number = get_node_serial(node_handle)
        ret_val = _handle_docker_volumes(serial_number, args, local_volumes, log)

    return ret_val
