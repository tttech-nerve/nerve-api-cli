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


"""Function for listing workloads"""

import gzip
import json
import logging
import os
import posixpath
import shutil
import tarfile
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from pathlib import Path

import yaml
from nerve_lib import CheckStatusCodeError

from .utils import args_interactive
from .utils import check_filter_arg
from .utils import clean_wl_definition
from .utils import docker_registry_workflow
from .utils import file_read
from .utils import file_write
from .utils import format_size_string
from .utils import size_string_to_bytes


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
        default="",
        help="Filter for specific workload type",
        choices=["docker", "codesys", "vm", "docker-compose"],
    )
    filter_args.add_argument(
        "-n",
        "--name",
        metavar="FILTER",
        default="",
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

    deploy_args.add_argument(
        "--registry", help=("Paste the copied Workload as a registry workload"), action="store_true"
    )

    deploy_args.add_argument(
        "--legacy", help=("Paste the copied Workload as a legacy workload"), action="store_true"
    )
    required_group = parser.add_argument_group("Mutually exclusive arguments for action")
    action_group = required_group.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "-l",
        "--list",
        help="List the workloads (and versions) and store results to 'file'",
        action="store_true",
    )
    action_group.add_argument(
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
        "--paste",
        help="Paste the workloads or versions specified in 'file' to the management system",
        action="store_true",
    )
    action_group.add_argument(
        "--delete", help="Delete the workloads or versions specified in 'file'", action="store_true"
    )
    action_group.add_argument(
        "--deploy",
        help="Deploy the workload version defined in 'file' to the nodes (within 'nodes_file')",
        action="store_true",
    )


def _ms_workloads_single_copy(  # noqa: PLR0912, PLR0914, PLR0915
    ms_workloads, args, wl_name, wl_internal_registry, wl_type, filtered_versions, log
):
    def create_ms_workloads_path(work_dir, path):
        """Create the path for storing the workloads files."""
        if not path:
            return
        full_path = os.path.join(work_dir, path)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
        return

    def reorder_wl_def_files(wl_definition: dict) -> tuple[dict, bool]:
        """Move all XML file entries to the end if non-XML files are present.
        Returns the potentially modified wl_definition and whether the file order changed.
        """
        versions = wl_definition.get("versions")
        if not isinstance(versions, list) or not versions:
            return wl_definition, False

        files = versions[0].get("files")
        if not isinstance(files, list) or len(files) < 2:  # noqa: PLR2004
            return wl_definition, False

        def is_xml_file(file_entry: dict) -> bool:
            file_name = (file_entry.get("originalName") or file_entry.get("name") or "").lower()
            return file_name.endswith(".xml")

        xml_files = [file_entry for file_entry in files if is_xml_file(file_entry)]
        non_xml_files = [file_entry for file_entry in files if not is_xml_file(file_entry)]

        # Reorder only when both groups exist; keep relative order within each group.
        if not xml_files or not non_xml_files:
            return wl_definition, False

        reordered_files = non_xml_files + xml_files
        changed = reordered_files != files
        if changed:
            versions[0]["files"] = reordered_files

        return wl_definition, changed

    if not filtered_versions:
        return

    # retrieve all workload version details and overwrite the filtered versions
    for i, version in enumerate(filtered_versions):  # noqa: PLR1702
        if not version.get("releaseName"):
            version.update({"releaseName": ""})
        if wl_internal_registry == True or wl_type == "docker-compose":
            api_version = 3
        else:
            api_version = 2
        container = ms_workloads.WorkloadVersion(
            wl_name, version["name"], version.get("releaseName")
        ).get_container(api_version=api_version)
        detailed_version = container.get("versions")[0]
        filtered_versions[i] = detailed_version

        release_version = (
            f"_{detailed_version.get('releaseName', '')}" if detailed_version.get("releaseName") else ""
        )
        save_path = os.path.join(args.path, wl_name, f"{detailed_version['name']}{release_version}")
        create_ms_workloads_path(args.work_dir, save_path)

        file_write(os.path.join(args.work_dir, save_path), "wl_def.json", container)

        wl_version = ms_workloads.WorkloadVersion(wl_name, version["name"], version.get("releaseName"))
        response = wl_version.export_workload_version(api_version=api_version)
        file_name = (
            response.headers
            .get("Content-Disposition", "attachment; filename=workload_file")
            .split("filename=")[-1]
            .strip('"')
        )

        destination_path = os.path.join(args.work_dir, save_path, file_name)
        if os.path.exists(destination_path):
            destination_path = os.path.join(args.work_dir, save_path, file_name)

        # Save the file to the specified path in chunks to handle large files
        with open(destination_path, "wb") as dest_file:
            for chunk in response.iter_content(chunk_size=8192):  # Stream in 8KB chunks
                if chunk:  # Filter out keep-alive new chunks
                    dest_file.write(chunk)
        log.info("Downloaded and saved file: %s", file_name)
        # untar the file
        files_contained = []
        if file_name.endswith((".tar.gz", ".tgz")):
            log.info("Extracting tar-gzipped file: %s (%s)", destination_path, file_name)
            with tarfile.open(destination_path, "r:gz") as tar:
                tar.extractall(path=os.path.join(args.work_dir, save_path))
                files_contained = tar.getnames()
            log.debug("Extracted files: %s", files_contained)
        if file_name.endswith(".tar"):
            with tarfile.open(destination_path, "r:") as tar:
                tar.extractall(path=os.path.join(args.work_dir, save_path))
                files_contained = tar.getnames()
            log.debug("Extracted files: %s", files_contained)
        os.remove(destination_path)
        json_content = None
        for file in files_contained:
            if file.endswith(".gz"):
                full_file_path = os.path.join(args.work_dir, save_path, file)
                log.info("Extracting gzipped file: %s (%s)", full_file_path, file)
                extracted_file = os.path.splitext(full_file_path)[0]
                with gzip.open(full_file_path, "rb") as f_in, open(extracted_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                log.debug("Extracted gzipped file: %s", extracted_file)
                os.remove(full_file_path)
            if file.endswith(".json"):
                log.info("JSON file included: %s", file)
                json_content = file_read(os.path.join(args.work_dir, save_path), file)
                wl_def_content = file_read(os.path.join(args.work_dir, save_path), "wl_def.json")

                if json_content["type"] == "docker-compose":
                    if not wl_def_content["versions"][0].get("workloadSpecificProperties"):
                        wl_def_content["versions"][0]["workloadSpecificProperties"] = json_content[
                            "version"
                        ].get("workloadSpecific", [{}])[0]
                    if not wl_def_content["versions"][0].get("selectors"):
                        wl_def_content["versions"][0]["selectors"] = json_content["version"].get(
                            "selectors", []
                        )
                    if not wl_def_content["versions"][0].get("remoteConnections"):
                        wl_def_content["versions"][0]["remoteConnections"] = json_content["version"].get(
                            "remoteConnections", []
                        )
                elif wl_def_content["type"] == "vm":
                    log.debug(
                        "Reordering file pathes for VM workload to ensure .xml file isnt first if present"
                    )
                    wl_def_content, wl_def_changed = reorder_wl_def_files(wl_def_content)
                    if wl_def_changed:
                        abs_wl_def_file_path = os.path.join(args.work_dir, save_path, "wl_def.json")
                        with open(abs_wl_def_file_path, "w", encoding="utf-8") as wl_def_file:
                            json.dump(wl_def_content, wl_def_file, indent=4)
                        log.debug("Updated wl_def file order and overwrote %s", abs_wl_def_file_path)

                file_write(
                    os.path.join(args.work_dir, save_path), "wl_def.json", clean_wl_definition(wl_def_content)
                )

        if json_content:
            for file_info in json_content["version"].get("files", []):
                name = (
                    file_info["name"].rsplit(".gz", 1)[0]
                    if file_info["name"].endswith(".gz")
                    else file_info["name"]
                )
                original_name = file_info["originalName"]
                # for docker registry workloads
                if original_name.startswith("registry/"):
                    original_name = os.path.basename(original_name).split(":", -1)[0] + file_info.get(
                        "type", ".tar"
                    )
                # move file with name to original name
                if (
                    name
                    and original_name
                    and name != original_name
                    and os.path.exists(os.path.join(args.work_dir, save_path, name))
                ):
                    os.rename(
                        os.path.join(args.work_dir, save_path, name),
                        os.path.join(args.work_dir, save_path, original_name),
                    )
                    log.info("Renamed file %s to %s", name, original_name)
                # if there is no original name specified in the JSON
                if (
                    name
                    and not original_name
                    and os.path.exists(os.path.join(args.work_dir, save_path, name))
                ):
                    log.warning("File '%s' has no original name specified in the JSON", name)
                    if file_info["sourceInfo"].get("file"):
                        original_name = file_info["sourceInfo"].get("file").split("/")[-1].split(":")[0]
                        if "." in name:
                            if name.endswith(".gz"):
                                file_suffix = "." + name.split(".")[-2] + "." + name.split(".")[-1]
                            else:
                                file_suffix = "." + name.split(".")[-1]
                        else:
                            file_suffix = ""
                        log.debug("Trying to rename file %s to %s based on sourceInfo", name, original_name)
                        if file_suffix:
                            os.rename(
                                os.path.join(args.work_dir, save_path, name),
                                os.path.join(args.work_dir, save_path, original_name + file_suffix),
                            )
                            log.info("Renamed file %s to %s", name, original_name + file_suffix)
                        else:
                            log.warning(
                                "Could not determine file suffix for file '%s', keeping the name as is", name
                            )


def _ms_workloads_copy(ms_workloads, args, log=None):
    for workload in file_read(args.work_dir, args.file):
        wl_name = workload["name"]
        wl_type = workload["type"]
        wl_internal_registry = workload.get("internalDockerRegistry", False)
        _ms_workloads_single_copy(
            ms_workloads, args, wl_name, wl_internal_registry, wl_type, workload["versions"], log
        )


def _ms_workloads_list(ms_workloads, args, log=None):  # noqa: PLR0915
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
                allowed_maximum = size_string_to_bytes(args.version_size_above)
                if wl_version["overall_size"] > allowed_maximum:
                    result_versions.append(wl_version)
            versions = deepcopy(result_versions)

        if args.version_date_older_than:
            result_versions = []
            for wl_version in versions:
                # get latest date from 'createdAt' or 'updatedAt'
                latest_mofification_date = datetime.strptime(
                    wl_version["createdAt"], "%Y-%m-%dT%H:%M:%S.%fZ"
                ).astimezone(UTC)
                if "updatedAt" in wl_version:
                    latest_mofification_date = datetime.strptime(
                        wl_version["updatedAt"], "%Y-%m-%dT%H:%M:%S.%fZ"
                    ).astimezone(UTC)

                allowed_date = datetime.strptime(args.version_date_older_than, "%Y-%m-%d").astimezone(UTC)
                if latest_mofification_date < allowed_date:
                    result_versions.append(wl_version)
            versions = deepcopy(result_versions)

        if args.version_list_filter:
            # sort versions by createdAt date descending
            versions_sorted = sorted(
                versions,
                key=lambda v: datetime.strptime(v["createdAt"], "%Y-%m-%dT%H:%M:%S.%fZ").astimezone(UTC),
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
                    raise ValueError("invalid")
            except ValueError:
                raise ValueError("Invalid version_list_filter format, provide start:end or index as integer")

        return versions

    def human_readable_output(wl_type, versions, wl_internal_registry):
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
                f"'{v_name}'/'{v_release_name}'"
                if v_release_name and v_name != v_release_name
                else f"'{v_name}'"
            )
            version_size_str = "0B"
            if "overall_size" in wl_version:
                version_size_str = format_size_string(wl_version["overall_size"])

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
    filter_name = args.name if "regex:" not in args.name else ""
    wl_list = ms_workloads.get_workloads_dict(
        read_versions=True, compact_dict=False, filter_name=filter_name, filter_type=args.type
    )

    # apply workload level filters
    for workload in wl_list:
        wl_name = workload["name"]
        if not check_filter_arg(args.name, wl_name):
            continue

        wl_id = workload["_id"]
        if not check_filter_arg(args.id, wl_id):
            continue

        if not args.disabled and check_filter_arg(True, workload["disabled"]):
            continue

        # apply version level filters
        filtered_versions = filter_versions(workload, args)
        if not filtered_versions:
            continue
        log.debug("Filtered versions for workload '%s': %s", wl_name, filtered_versions)

        wl_internal_registry = workload.get("internalDockerRegistry", False)
        human_readable_output(workload["type"], filtered_versions, wl_internal_registry)

        wl_output = deepcopy(workload)
        wl_output["versions"] = filtered_versions
        output.append(wl_output)

    # Check if all workload details can be read successfully
    failed_count = 0
    for workload in output:
        for version in workload["versions"]:
            try:
                if workload.get("type") == "docker-compose" or (
                    workload.get("type") == "docker" and workload.get("internalDockerRegistry")
                ):
                    ms_workloads.WorkloadVersion(
                        workload["name"], version["name"]
                    ).get_additional_version_details()
            except CheckStatusCodeError as ex_msg:
                log.warning(
                    "Failed to read details for workload '%s', version '%s': %s",
                    workload["name"],
                    version["name"],
                    ex_msg,
                )
                failed_count += 1

    file_write(args.work_dir, args.file, output)
    if not output:
        log.warning("No workloads found with the provided filters")
        return 1
    return failed_count


def _ms_workloads_delete(ms_workloads, args, log=None):
    for workload in file_read(args.work_dir, args.file):
        for version in workload["versions"]:
            try:
                wl_version = ms_workloads.WorkloadVersion(
                    workload["name"], version["name"], version.get("releaseName")
                )
                wl_version.delete_workload_version()
            except ValueError as ex_msg:
                raise ValueError(f"Workload version cannot be removed: {ex_msg}")
        wl_version = ms_workloads.WorkloadVersion(workload["name"])
        if not wl_version._get_versions():
            # all sub-version had been removed, deleting also the workload
            wl_version.delete_workload()


def _ms_workloads_deploy(ms_workloads, ms_nodes, args, log=None):
    nodes = file_read(args.work_dir, args.nodes_file)
    workloads = file_read(args.work_dir, args.file)

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


def _ms_workloads_paste(ms_workloads, args, log=None):  # noqa: PLR0912, PLR0914, PLR0915
    workloads = file_read(args.work_dir, args.file) or []

    def parse_yml_for_images(yml_path, target_url):
        """Parse the YML file to extract repository and tag information from 'image' keys."""
        with open(yml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        images = []
        if "services" in data:
            for service in data["services"].values():
                if "image" in service:
                    image = service["image"]
                    if ":" in image:
                        repo, tag = image.rsplit(":", 1)
                    else:
                        repo = image
                        tag = "latest"
                    images.append((repo, tag))
        return images

    def create_modified_yml(yml_path, target_url):
        """Create a modified copy of the YML file with updated image URLs."""
        with open(yml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if "services" in data:
            for service in data["services"].values():
                if "image" in service:
                    image = service["image"]
                    if "/registry/" in image:
                        repo_part = image.split("/registry/")[0]
                        service["image"] = image.replace(repo_part, target_url, 1)
                    else:
                        service["image"] = target_url + "/registry/" + image
        # overwrite the original yml file
        with open(yml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                indent=4,
                encoding=None,
            )
        return yml_path

    def modify_wl_def_registry_type(wl_def_file_path, wl_def, workloadtype):
        log.debug("Modifying wl_def '%s' for workload type '%s'", wl_def_file_path, workloadtype)
        if workloadtype == "registry":
            wl_def["internalDockerRegistry"] = True
        elif workloadtype == "legacy":
            wl_def["internalDockerRegistry"] = False
        with open(wl_def_file_path, "w", encoding="utf-8") as f:
            json.dump(wl_def, f, indent=4)
        return wl_def

    def create_individual_workload(wl_def, wl_file_paths: list):
        if type(wl_def) is not dict:
            raise TypeError("Workload definition must be a dictionary")
        if wl_def["type"] == "docker-compose" or wl_def.get("internalDockerRegistry") == True:
            api_version = 3
        else:
            api_version = 2

        search_pathes = [posixpath.join(args.work_dir, file_path) for file_path in wl_file_paths]
        file_pathes = []
        for search_path in search_pathes:
            file_pathes += sorted([file_path.as_posix() for file_path in Path.cwd().glob(search_path)])
        log.debug("Working with file pathes: \n    - %s", "\n    - ".join(file_pathes))
        wl = clean_wl_definition(wl_def)
        ms_workloads.provision_workload(wl, file_pathes, api_version)

    for workload in workloads:  # noqa: PLR1702
        wl_name = workload["name"]
        wl_type = workload["type"]

        log.info(
            "Pasting Workload to MS '%s' (%s)...",
            wl_name,
            wl_type,
        )

        for version in workload["versions"]:
            version_name = version["name"]
            version_release_name = f"_{version.get('releaseName', '')}" if version.get("releaseName") else ""
            log.info(
                "    Version '%s%s'...",
                version_name,
                version_release_name,
            )
            wl_file_root_path = os.path.join(args.path, wl_name, f"{version_name}{version_release_name}")
            wl_def_file_path = os.path.join(wl_file_root_path, "wl_def.json")
            wl_def = file_read(args.work_dir, wl_def_file_path)
            wl_file_paths = []
            wl_root_path = Path(os.path.join(args.work_dir, wl_file_root_path))
            if wl_type == "docker-compose":
                if wl_def.get("internalDockerRegistry") == False and args.registry:
                    wl_def = modify_wl_def_registry_type(
                        os.path.join(args.work_dir, wl_def_file_path), wl_def, "registry"
                    )
                elif wl_def.get("internalDockerRegistry") == True and args.legacy:
                    wl_def = modify_wl_def_registry_type(
                        os.path.join(args.work_dir, wl_def_file_path), wl_def, "legacy"
                    )
                wl_root_path = Path(os.path.join(args.work_dir, wl_file_root_path))
                # use all tar files and yml files in the folder as workload files for docker-compose workloads
                for pattern in ("*.tar", "*.tar.gz"):
                    for file_path in wl_root_path.glob(pattern):
                        wl_file_paths.append(str(file_path.relative_to(args.work_dir)))
                if wl_def.get("internalDockerRegistry") == True:
                    target_url = ms_workloads.ms.ms_url
                    yml_files = list(wl_root_path.glob("*.yml")) or list(wl_root_path.glob("*.yaml"))
                    for yml_file in yml_files:
                        modified_yml = create_modified_yml(str(yml_file), target_url)
                        wl_file_paths.append(str(Path(modified_yml).relative_to(args.work_dir)))
                    for file_path in wl_file_paths[:]:
                        if file_path.endswith((".yml", ".yaml")):
                            yml_path = os.path.join(args.work_dir, file_path)
                            images = parse_yml_for_images(yml_path, target_url)
                            log.debug("Parsed images from YML: %s", images)
                            for repo, tag in images:
                                docker_registry_workflow(args.work_dir, wl_file_paths, repo, tag)
                    for file_path in wl_file_paths[:]:
                        if not file_path.endswith((".yml", ".yaml")):
                            wl_file_paths.remove(file_path)
                else:
                    # if not using internal Docker registry, include all yml and yaml files
                    for pattern in ("*.yml", "*.yaml"):
                        for file_path in wl_root_path.glob(pattern):
                            wl_file_paths.append(str(file_path.relative_to(args.work_dir)))
            elif wl_type == "docker" and wl_def.get("internalDockerRegistry") == True:
                for pattern in ("*.tar", "*.tar.gz", "*.json"):
                    for file_path in wl_root_path.glob(pattern):
                        wl_file_paths.append(str(file_path.relative_to(args.work_dir)))
                target_url = ms_workloads.ms.ms_url
                images = []
                for file_path in wl_file_paths[:]:
                    log.debug("Checking file '%s' for docker image information", file_path)
                    if file_path.endswith(".json") and not file_path.endswith("wl_def.json"):
                        log.debug("Reading JSON file from %s, %s", args.work_dir, file_path)
                        json_content = file_read(args.work_dir, file_path)
                        if json_content:
                            log.debug("Read JSON succcess")
                            if json_content["type"] == "docker":
                                for file_info in json_content["version"].get("files", []):
                                    if file_info["sourceInfo"]["type"] == "docker-image":
                                        repo, tag = file_info["sourceInfo"]["source"].split(":")
                                        images.append((repo, tag))
                log.debug("Parsed images from JSON files: %s", images)
                for repo, tag in images:
                    repo_mod = (
                        target_url + "/registry/" + repo.split("registry/")[-1]
                    )  # results in "<ms_url>/registry/<wl-name>"
                    log.debug("Processing image with repo '%s' and tag '%s'", repo_mod, tag)
                    docker_registry_workflow(args.work_dir, wl_file_paths, repo, tag)
                for file_path in wl_file_paths[:]:
                    if not file_path.endswith(".json"):
                        wl_file_paths.remove(file_path)
            else:
                for file in version.get("files", []):
                    file_path = os.path.join(wl_file_root_path, file["originalName"])
                    if os.path.exists(os.path.join(args.work_dir, file_path)):
                        wl_file_paths.append(file_path)
                    else:
                        raise FileNotFoundError(
                            "File '%s' defined in workload version '%s' not found at path '%s'",
                            file["name"],
                            version_name,
                            file_path,
                        )

            log.info(
                "Found files for workload '%s', version '%s': \n    - %s",
                wl_name,
                version_name,
                "\n    - ".join(wl_file_paths),
            )
            create_individual_workload(wl_def, wl_file_paths)


def ms_workloads(ms_workloads, ms_nodes, arg, log=None):
    log = log.getChild(__name__.split(".")[-1]) if log else logging.getLogger(__name__)
    args = args_interactive(
        arg,
        args_ms_workloads,
        "Operate on workloads of the management system.",
    )
    if not args:
        log.error("Failed to parse arguments")
        return 2

    if args.copy:
        return _ms_workloads_copy(ms_workloads, args, log)
    if args.list:
        return _ms_workloads_list(ms_workloads, args, log)
    if args.paste:
        return _ms_workloads_paste(ms_workloads, args, log)
    if args.delete:
        return _ms_workloads_delete(ms_workloads, args, log)
    if args.deploy:
        return _ms_workloads_deploy(ms_workloads, ms_nodes, args, log)

    log.error("No valid action specified")
    return 2
