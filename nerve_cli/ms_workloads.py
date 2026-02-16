# Copyright (c) 2024 TTTech Industrial Automation AG.
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


"""Function for listing workloads"""

import gzip
import logging
import os
import shutil
import tarfile
from copy import deepcopy
from datetime import datetime

from .utils import args_interactive
from .utils import check_filter_arg
from .utils import clean_wl_definition
from .utils import file_read
from .utils import file_write


def args_ms_workloads(parser):
    parser.add_argument(
        "-f",
        "--file",
        metavar="FILE_NAME",
        default="workloads.json",
        help="Specify the file name for storing and reading workloads from. Defaults to 'workloads.json' if omitted. '.json' is appended if not included.",
    )
    parser.add_argument(
        "-p",
        "--path",
        metavar="PATH_NAME",
        default="workload_files",
        help="Specify the path name for storing and reading workload files from. Defaults to 'workload_files' if omitted.",
    )
    filter_args = parser.add_argument_group("Filter arguments for getting workloads list")
    filter_args.add_argument(
        "-t",
        "--type",
        metavar="FILTER",
        help="Filter for specific workload type",
        choices=["docker", "codesys", "vm", "docker-compose"],
    )
    filter_args.add_argument(
        "-n",
        "--name",
        metavar="FILTER",
        help="Filter by name, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_args.add_argument(
        "--id",
        metavar="FILTER",
        help="Filter by ID, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_args.add_argument(
        "--disabled", help="Include disabled workloads in the results.", action="store_true"
    )
    filter_args.add_argument(
        "-v",
        "--version_name",
        metavar="FILTER",
        help="Filter by version name, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_args.add_argument(
        "-r",
        "--version_release_name",
        metavar="FILTER",
        help="Filter by version release name, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_args.add_argument(
        "--version_size_above",
        metavar="FILTER",
        help="Filter Workloads with file size above the given value (e.g. '4GB' or '100MB', must end with one of GB, MB, KB, B).",
    )
    filter_args.add_argument(
        "--version_date_older_than",
        metavar="FILTER",
        help="Filter Workloads with version date older than the given value (date in format 'YYYY-MM-DD').",
    )
    filter_args.add_argument(
        "--version_list_filter",
        metavar="<start>:<end>",
        help=(
            "Filter workload versions (sorted by creation date) to be listed by providing a range similar to list slicing in Python."
            " E.g., '0:5' lists the first 5 versions, '-5:' the last 5 versions, '3' the 4th version only."
        ),
    )

    deploy_args = parser.add_argument_group("Optional arguments for workloads deployment")
    deploy_args.add_argument(
        "--nodes_file",
        metavar="FILE_NAME",
        default="nodes.json",
        help="Specify the file name which is listing the nodes to operate on. Defaults to 'nodes.json' if omitted. '.json' is appended if not included.",
    )
    deploy_args.add_argument("--wait", help="Wait for the deployment to finish.", action="store_true")

    required_group = parser.add_argument_group("Mutually exclusive arguments for action")
    action_group = required_group.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "-l",
        "--list",
        help="List the workloads (and versions) and store results to 'file'",
        action="store_true",
    )
    action_group.add_argument(
        "-c",
        "--copy",
        help=(
            "Downloads the workload version, storing the workload definitions to"
            " 'file' (similar to --list). Within <path>/<workload_name>/<version_name>/ a wl_def.json"
            " and all associated files are stored (untarred and un-gzipped as needed) where <path>"
            " is the value provided to the --path argument."
        ),
        action="store_true",
    )
    action_group.add_argument(
        "--delete", help="Delete the workloads or versions specified in 'file'", action="store_true"
    )
    action_group.add_argument(
        "-d",
        "--deploy",
        help="Deploy the workload version defined in 'file' to the nodes (within 'nodes_file')",
        action="store_true",
    )


def _ms_workloads_copy(ms_workloads, work_dir, args, wl_name, filtered_versions, log):
    def create_ms_workloads_path(work_dir, path):
        """Create the path for storing the workloads files."""
        if not path:
            return
        full_path = os.path.join(work_dir, path)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
        return

    if not filtered_versions:
        return

    # retrieve all workload version details and overwrite the filtered versions
    for i, version in enumerate(filtered_versions):
        container = ms_workloads.WorkloadVersion(
            wl_name, version["name"], version.get("releaseName")
        ).get_container()
        detailed_version = container.get("versions")[0]
        filtered_versions[i] = detailed_version

        save_path = os.path.join(args.path, wl_name, version["name"])
        create_ms_workloads_path(work_dir, save_path)

        file_write(os.path.join(work_dir, save_path), "wl_def.json", container)

        wl_version = ms_workloads.WorkloadVersion(wl_name, version["name"], version.get("releaseName"))
        response = wl_version.export_workload_version()
        file_name = (
            response.headers.get("Content-Disposition", "attachment; filename=workload_file")
            .split("filename=")[-1]
            .strip('"')
        )

        destination_path = os.path.join(work_dir, save_path, file_name)
        if os.path.exists(destination_path):
            destination_path = os.path.join(work_dir, save_path, file_name)

        # Save the file to the specified path in chunks to handle large files
        with open(destination_path, "wb") as dest_file:
            for chunk in response.iter_content(chunk_size=8192):  # Stream in 8KB chunks
                if chunk:  # Filter out keep-alive new chunks
                    dest_file.write(chunk)
        log.info("Downloaded and saved file: %s", file_name)
        # untar the file
        files_contained = []
        if file_name.endswith(".tar.gz") or file_name.endswith(".tgz"):
            log.info("Extracting tar-gzipped file: %s (%s)", destination_path, file_name)
            with tarfile.open(destination_path, "r:gz") as tar:
                tar.extractall(path=os.path.join(work_dir, save_path))
                files_contained = tar.getnames()
            log.debug("Extracted files: %s", files_contained)
        if file_name.endswith(".tar"):
            with tarfile.open(destination_path, "r:") as tar:
                tar.extractall(path=os.path.join(work_dir, save_path))
                files_contained = tar.getnames()
            log.debug("Extracted files: %s", files_contained)
        os.remove(destination_path)
        json_content = None
        for file in files_contained:
            if file.endswith(".gz"):
                full_file_path = os.path.join(work_dir, save_path, file)
                log.info("Extracting gzipped file: %s (%s)", full_file_path, file)
                extracted_file = os.path.splitext(full_file_path)[0]
                with gzip.open(full_file_path, "rb") as f_in:
                    with open(extracted_file, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                log.debug("Extracted gzipped file: %s", extracted_file)
                os.remove(full_file_path)
            if file.endswith(".json"):
                log.info("JSON file included: %s", file)
                json_content = file_read(os.path.join(work_dir, save_path), file)
                wl_def_content = file_read(os.path.join(work_dir, save_path), "wl_def.json")

                if json_content["type"] == "docker-compose":
                    wl_def_content["versions"][0]["workloadSpecificProperties"] = json_content["version"].get(
                        "workloadSpecific", [{}]
                    )[0]
                    wl_def_content["versions"][0]["selectors"] = json_content["version"].get("selectors", [])
                    wl_def_content["versions"][0]["remoteConnections"] = json_content["version"].get(
                        "remoteConnections", []
                    )

                file_write(
                    os.path.join(work_dir, save_path), "wl_def.json", clean_wl_definition(wl_def_content)
                )

        if json_content:
            for file_info in json_content["version"].get("files", []):
                name = (
                    file_info["name"].rsplit(".gz", 1)[0]
                    if file_info["name"].endswith(".gz")
                    else file_info["name"]
                )
                original_name = file_info["originalName"]
                # move file with name to original name
                if name and original_name and name != original_name:
                    if os.path.exists(os.path.join(work_dir, save_path, name)):
                        os.rename(
                            os.path.join(work_dir, save_path, name),
                            os.path.join(work_dir, save_path, original_name),
                        )
                        log.info("Renamed file %s to %s", name, original_name)


def _ms_workloads_list(ms_workloads, work_dir, args, log=None, copy=None):  # noqa: PLR0915
    def filter_versions(workload, args):
        versions = workload["versions"]
        versions = [v for v in versions if check_filter_arg(args.version_name, v["name"])]
        versions = [v for v in versions if check_filter_arg(args.version_release_name, v.get("releaseName"))]

        for wl_version in versions:
            overall_size = 0
            for file in wl_version.get("files", []):
                overall_size += int(file["size"])
            wl_version["overall_size"] = overall_size

        if args.version_size_above:
            result_versions = []
            for wl_version in versions:
                # convert 100MB or 4GB to bytes
                if args.version_size_above[-2:] == "KB":
                    allowed_maximum = float(args.version_size_above[:-2]) * 1024
                elif args.version_size_above[-2:] == "MB":
                    allowed_maximum = float(args.version_size_above[:-2]) * 1024 * 1024
                elif args.version_size_above[-2:] == "GB":
                    allowed_maximum = float(args.version_size_above[:-2]) * 1024 * 1024 * 1024
                elif args.version_size_above[-1] == "B":
                    allowed_maximum = float(args.version_size_above[:-1])
                else:
                    raise ValueError("Invalid size format, must end with one of GB, MB, KB, B")
                allowed_maximum = int(allowed_maximum)

                if wl_version["overall_size"] > allowed_maximum:
                    result_versions.append(wl_version)
            versions = deepcopy(result_versions)

        if args.version_date_older_than:
            result_versions = []
            for wl_version in versions:
                # get latest date from 'createdAt' or 'updatedAt'
                latest_mofification_date = datetime.strptime(wl_version["createdAt"], "%Y-%m-%dT%H:%M:%S.%fZ")
                if "updatedAt" in wl_version:
                    latest_mofification_date = datetime.strptime(
                        wl_version["updatedAt"], "%Y-%m-%dT%H:%M:%S.%fZ"
                    )

                allowed_date = datetime.strptime(args.version_date_older_than, "%Y-%m-%d")
                if latest_mofification_date < allowed_date:
                    result_versions.append(wl_version)
            versions = deepcopy(result_versions)

        if args.version_list_filter:
            # sort versions by createdAt date descending
            versions_sorted = sorted(
                versions,
                key=lambda v: datetime.strptime(v["createdAt"], "%Y-%m-%dT%H:%M:%S.%fZ"),
                reverse=False,
            )
            # apply slicing
            try:
                slice_parts = args.version_list_filter.split(":")
                if len(slice_parts) == 2:  # noqa: PLR2004
                    start = int(slice_parts[0]) if slice_parts[0] else None
                    end = int(slice_parts[1]) if slice_parts[1] else None
                    versions = versions_sorted[start:end]
                elif len(slice_parts) == 1:
                    index = int(slice_parts[0])
                    versions = [versions_sorted[index]]
                else:
                    raise ValueError("Invalid version_list_filter format.")
            except Exception:
                raise ValueError("Invalid version_list_filter format.")

        return versions

    def human_readable_output(versions):
        log.info(
            "%s%s Workload '%s' (%s):",
            wl_type,
            " (internal registry)" if wl_internal_registry else "",
            wl_name,
            wl_id,
        )

        for wl_version in versions:
            v_name = wl_version["name"]
            v_release_name = wl_version.get("releaseName", None)
            version_str = (
                "'%s'/'%s'" % (v_name, v_release_name)
                if v_release_name and v_name != v_release_name
                else "'%s'" % v_name
            )
            version_size_str = "0B"
            if "overall_size" in wl_version:
                if wl_version["overall_size"] > 1024 * 1024 * 1024 * 10:
                    version_size_str = f"{wl_version['overall_size'] / (1024 * 1024 * 1024):.2f}GB"
                elif wl_version["overall_size"] > 1024 * 1024 * 10:
                    version_size_str = f"{wl_version['overall_size'] / (1024 * 1024):.2f}MB"
                elif wl_version["overall_size"] > 1024 * 10:
                    version_size_str = f"{wl_version['overall_size'] / 1024:.2f}KB"
                else:
                    version_size_str = f"{wl_version['overall_size']}B"

            container_name_str = ""
            if wl_type == "docker":
                if "workloadProperties" in wl_version:
                    container_name_str = (
                        f" Container name: '{wl_version['workloadProperties'].get('container_name', '')}'"
                    )
                elif "workloadSpecificProperties" in wl_version:
                    container_name_str = f" Container name: '{wl_version['workloadSpecificProperties'].get('container_name', '')}'"

            log.info(
                "    Version %s (%s)%s",
                version_str,
                version_size_str,
                container_name_str,
            )

    # ms_workloads_list main function
    output = []

    # get full list of all workloads
    wl_list = ms_workloads.get_workloads_dict(
        read_versions=True, read_compose_details=True, compact_dict=False
    )

    # apply workload level filters
    for workload in wl_list:
        wl_name = workload["name"]
        if not check_filter_arg(args.name, wl_name):
            continue

        wl_type = workload["type"]
        if not check_filter_arg(args.type, wl_type):
            continue

        wl_id = workload["_id"]
        if not check_filter_arg(args.id, wl_id):
            continue

        if not args.disabled:
            if check_filter_arg(True, workload["disabled"]):
                continue

        wl_internal_registry = workload.get("internalDockerRegistry", False)

        # apply version level filters
        filtered_versions = filter_versions(workload, args)
        if not filtered_versions:
            continue

        if copy:
            _ms_workloads_copy(ms_workloads, work_dir, args, wl_name, filtered_versions, log)

        human_readable_output(filtered_versions)

        wl_output = deepcopy(workload)
        wl_output["versions"] = filtered_versions
        output.append(wl_output)

    file_write(work_dir, args.file, output)


def _ms_workloads_delete(ms_workloads, work_dir, args, log=None):
    for workload in file_read(work_dir, args.file):
        for version in workload["versions"]:
            try:
                wl_version = ms_workloads.WorkloadVersion(
                    workload["name"], version["name"], version.get("releaseName")
                )
                wl_version.delete_workload_version()
            except ValueError as ex_msg:
                log.warning("Workload version cannot be removed: %s", ex_msg)
        wl_version = ms_workloads.WorkloadVersion(workload["name"])
        if not wl_version._get_versions():
            # all sub-version had been removed, deleting also the workload
            wl_version.delete_workload()


def _ms_workloads_deploy(ms_workloads, ms_nodes, work_dir, args, log=None):
    nodes = file_read(work_dir, args.nodes_file)
    workloads = file_read(work_dir, args.file)

    node_list = []

    for node in nodes:
        node_handle = ms_nodes.Node(node["serialNumber"])
        node_list.append(node_handle)

    for workload in workloads:
        if len(workload.get("versions", [])) > 1:
            log.warning(
                "Workload %s has no specific version defined, last version will be selected",
                workload["name"],
            )
            version = workload["versions"][-1]
            wl_version = ms_workloads.WorkloadVersion(
                workload["name"], version["name"], version.get("releaseName")
            )
        elif len(workload.get("versions", [])) == 0:
            log.warning(
                "Workload %s has no specific version defined, latest version will be selected",
                workload["name"],
            )
            wl_version = ms_workloads.WorkloadVersion(workload["name"])
        else:
            version = workload["versions"][-1]
            wl_version = ms_workloads.WorkloadVersion(
                workload["name"], version["name"], version.get("releaseName")
            )
        if args.wait:
            wl_version.deploy_full(node_list)
        else:
            wl_version.deploy(node_list)


def ms_workloads(ms_workloads, ms_nodes, work_dir, arg, log=None):
    if not log:
        log = logging.getLogger(__name__)
    args = args_interactive(
        arg,
        args_ms_workloads,
        "Operate on workloads of the management system.",
    )
    if not args:
        return

    # Process the arguments as needed
    if args.copy:
        _ms_workloads_list(ms_workloads, work_dir, args, log, copy=True)
    if args.list:
        _ms_workloads_list(ms_workloads, work_dir, args, log, copy=False)
    if args.delete:
        _ms_workloads_delete(ms_workloads, work_dir, args, log)
    if args.deploy:
        _ms_workloads_deploy(ms_workloads, ms_nodes, work_dir, args, log)
