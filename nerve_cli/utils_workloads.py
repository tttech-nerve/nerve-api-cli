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


"""Functions to support cli commands."""

from datetime import UTC
from datetime import datetime

from nerve_lib import CheckStatusCodeError

from .utils import format_size_string
from .utils import match_filter
from .utils import size_string_to_bytes


def _parse_comparison_filter(filter_value, option_name):
    """Parse comparison filters in symbolic or textual format.

    Supported formats:
    - symbolic: ">VALUE" or "<VALUE"
    - textual: "gt:VALUE" or "lt:VALUE"
    """
    normalized = filter_value.strip()
    if normalized.startswith(">"):
        return ">", normalized[1:]
    if normalized.startswith("<"):
        return "<", normalized[1:]

    lower_val = normalized.lower()
    if lower_val.startswith("gt:"):
        return ">", normalized[3:]
    if lower_val.startswith("lt:"):
        return "<", normalized[3:]

    raise ValueError(
        f"Invalid format for --{option_name}. Expected '>VALUE', '<VALUE', 'gt:VALUE', or 'lt:VALUE'."
    )


def check_filter_arg(cmd_line_filter, data_value):
    """Check if the argument is a filter and return the filter.
    If cmd_line_filter is not defined, return True."""

    if not cmd_line_filter:
        return True
    ret_val = False

    if cmd_line_filter:
        if isinstance(cmd_line_filter, (bool, int)):
            ret_val = cmd_line_filter == data_value
        elif isinstance(data_value, str):
            ret_val = match_filter(cmd_line_filter, data_value)
        else:
            ret_val = cmd_line_filter == data_value

    return ret_val


def filter_versions(workload, args):
    versions = workload["versions"]
    versions = [v for v in versions if check_filter_arg(args.version_name, v["name"])]
    versions = [v for v in versions if check_filter_arg(args.version_release_name, v.get("releaseName"))]

    for wl_version in versions:
        overall_size = 0
        for file in wl_version.get("files", []):
            overall_size += int(file.get("size", 0))
        wl_version["overall_size"] = overall_size

    if args.version_size:
        size_filter = args.version_size
        operator, threshold_value = _parse_comparison_filter(size_filter, "version-size")
        size_threshold = size_string_to_bytes(threshold_value)

        if operator and size_threshold is not None:
            if operator == ">":
                versions = [
                    v
                    for v in versions
                    if v.get("overall_size", 0) > size_threshold and v.get("overall_size", 0) != 0
                ]
            elif operator == "<":
                versions = [
                    v
                    for v in versions
                    if v.get("overall_size", 0) < size_threshold and v.get("overall_size", 0) != 0
                ]

    if args.version_date:
        date_filter = args.version_date
        operator, threshold_value = _parse_comparison_filter(date_filter, "version-date")
        date_threshold = datetime.strptime(threshold_value, "%Y-%m-%d").astimezone(UTC)
        if operator and date_threshold is not None:
            if operator == ">":
                versions = [
                    v
                    for v in versions
                    if datetime.strptime(v["createdAt"], "%Y-%m-%dT%H:%M:%S.%fZ").astimezone(UTC)
                    > date_threshold
                    or (
                        "updatedAt" in v
                        and datetime.strptime(v["updatedAt"], "%Y-%m-%dT%H:%M:%S.%fZ").astimezone(UTC)
                        > date_threshold
                    )
                ]
            elif operator == "<":
                versions = [
                    v
                    for v in versions
                    if datetime.strptime(v["createdAt"], "%Y-%m-%dT%H:%M:%S.%fZ").astimezone(UTC)
                    < date_threshold
                    or (
                        "updatedAt" in v
                        and datetime.strptime(v["updatedAt"], "%Y-%m-%dT%H:%M:%S.%fZ").astimezone(UTC)
                        < date_threshold
                    )
                ]

    if args.version_list_filter:
        # sort versions by createdAt date descending
        versions_sorted = sorted(
            versions,
            key=lambda v: datetime.strptime(v["createdAt"], "%Y-%m-%dT%H:%M:%S.%fZ").astimezone(UTC),
            reverse=False,
        )
        # apply slicing
        try:  # noqa: PLW0717
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
        except IndexError:
            versions = []  # if index is out of range, return empty list

    return versions


def human_readable_output(workload_list, log):
    for workload in workload_list:
        wl_type = workload["type"]
        wl_name = workload["name"]
        versions = workload["versions"]
        wl_internal_registry = workload.get("internalDockerRegistry", False)

        log.info(
            "%s%s Workload '%s':", wl_type, " (internal registry)" if wl_internal_registry else "", wl_name
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


def validate_ms_workload_read_error(workload_list, ms_workloads, log):
    failed_count = 0
    log.debug("Validating workload details can be read for docker-compose and internal docker workloads...")
    for workload in workload_list:
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
    return failed_count


def normalize_workloads_input(workloads, args, ms_workloads, log):
    """Normalize the workload definitions.

    Ensure each workload is aligned with the management system's workload definitions and contains
    necessary information for operations."""
    normalized_workloads = []
    fetched_workloads = []
    if isinstance(workloads, dict):
        workloads = [workloads]

    for filer_name, arg_value in {
        "--version-name": args.version_name or "",
        "--version-release-name": args.version_release_name or "",
    }.items():
        if arg_value.startswith(("regex:", "regexp:")):
            log.info(
                "Filtering workloads by '%s' with regex pattern: '%s'", filer_name, arg_value.split(":", 1)[1]
            )

    for workload in workloads:
        required_keys = {"name", "type", "_id", "versions"}
        if required_keys.issubset(workload):
            referece_workload = workload
        else:
            for key, value in workload.items():
                if not fetched_workloads or value not in any(wl.get(key) for wl in fetched_workloads):
                    # If workload is not in list of all_workloads
                    new_workloads = ms_workloads.get_workloads_dict(
                        read_versions=True,
                        compact_dict=False,
                        filter_name=workload.get("name"),
                        filter_type=workload.get("type"),
                    )
                    fetched_workloads.extend(new_workloads)
                    break

            referece_workload = next(
                (wl for wl in fetched_workloads if all(wl.get(k) == v for k, v in workload.items())), None
            )
        if not referece_workload:
            log.warning(
                "No matching workload found for workload definition: %s. Skipping this workload.",
                workload,
            )
            continue

        # Apply filters for versions
        filtered_versions = filter_versions(referece_workload, args)
        version_filter_defined = (
            args.version_name
            or args.version_release_name
            or args.version_size
            or args.version_date
            or args.version_list_filter
        )
        if not filtered_versions and version_filter_defined:
            log.debug("No versions matched the version-filters for workload '%s'", workload["name"])
            continue
        normalized_workload = referece_workload.copy()
        normalized_workload["versions"] = filtered_versions
        normalized_workloads.append(normalized_workload)

    return normalized_workloads
