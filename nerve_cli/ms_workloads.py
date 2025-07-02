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

import logging
import os
import requests
from copy import deepcopy
from datetime import datetime

from .utils import args_interactive
from .utils import check_filter_arg
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
        "-l", "--list", help="List the workloads (and versions) and store results to 'file'", action="store_true"
    )
    action_group.add_argument(
        "-c",
        "--copy",
        help="Downloads the workload version, storing the workload definitions to 'file' and the workload files to 'path'",
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


def _ms_workloads_copy(ms_workloads, work_dir, args, wl_name, filtered_versions, log=None):
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

    create_ms_workloads_path(work_dir, args.path)

    # retrieve all workload version details and overwrite the filtered versions
    for i, version in enumerate(filtered_versions):
        detailed_version = (
            ms_workloads.WorkloadVersion(wl_name, version["name"], version.get("releaseName"))
            .get_container()
            .get("versions")[0]
        )
        filtered_versions[i] = detailed_version

        for file in detailed_version.get("files", []):
            file_path = file.get("path")
            if not file_path:
                continue

            # Use the version export function from manage_workloads
            wl_version = ms_workloads.WorkloadVersion(wl_name, version["name"], version.get("releaseName"))
            response = wl_version.export_workload_version()
            if not response:
                if log:
                    log.error(f"Failed to export workload version: {version['name']}")
                continue

            if response.status_code == requests.codes.ok:
                file_name = file.get('originalName') or os.path.basename(file_path)

                # Handle file extensions, including cases like .tar.gz
                base_name, ext = os.path.splitext(file_name)
                if base_name.endswith('.tar'):
                    base_name, tar_ext = os.path.splitext(base_name)
                    ext = tar_ext + ext

                # Check if the file already exists, append version ID if necessary
                destination_path = os.path.join(work_dir, args.path, file_name)
                if os.path.exists(destination_path):
                    version_id = detailed_version.get("id")
                    file_name = f"{base_name}_{version_id}{ext}"
                    destination_path = os.path.join(work_dir, args.path, file_name)

                # If the file still exists, append the file ID
                if os.path.exists(destination_path):
                    file_id = file.get("id")
                    file_name = f"{base_name}_{version_id}_{file_id}{ext}"
                    destination_path = os.path.join(work_dir, args.path, file_name)

                # Save the file to the specified path in chunks to handle large files
                with open(destination_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):  # Stream in 8KB chunks
                        if chunk:  # Filter out keep-alive new chunks
                            f.write(chunk)
                if log:
                    log.info(f"Downloaded and saved file: {file_name}")
            else:
                if log:
                    log.error(f"Failed to download file: {file_path}. Status code: {response.status_code}")


def _ms_workloads_list(ms_workloads, work_dir, args, log=None, copy=None):
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

        return versions

    def human_readable_output(versions):
        log.info("%s Workload '%s' (%s):", wl_type, wl_name, wl_id)

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
                "Version %s (%s)%s",
                version_str,
                version_size_str,
                container_name_str,
            )

    # ms_workloads_list main function
    output = []

    # get full list of all workloads
    wl_list = ms_workloads.get_workloads_dict(
        read_versions=True, read_compose_details=False, compact_dict=False
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


def ms_workloads(ms_workloads, ms_nodes, work_dir, arg, log=None):  # noqa: PLR0914
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
