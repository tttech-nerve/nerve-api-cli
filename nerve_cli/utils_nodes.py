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

import json
import operator
import re

from .ms_nodes_remote_connections import get_existing_remotes


def args_ms_node_filters(parser):
    filter_args = parser.add_argument_group("Filter arguments for getting nodes list")
    filter_args.add_argument(
        "--model",
        metavar="MODEL",
        default="",
        help="Filter by node model (e.g., 'MFN-100', 'MFN-200')",
    )
    filter_args.add_argument(
        "--name",
        metavar="PATTERN",
        default="",
        help="Filter by node name. Supports regex with prefix 'regex:' (e.g., 'regex:node_[0-9]+', 'mynode')",
    )
    filter_args.add_argument(
        "--serial-number",
        metavar="PATTERN",
        help="Filter by serial number. Supports regex with prefix 'regex:' (e.g., 'regex:SN.*')",
    )
    filter_args.add_argument("--online", help="Include only online nodes", action="store_true")
    filter_args.add_argument(
        "--labels",
        metavar="PATTERN",
        help="Filter by node labels (format: 'key=label_key/value=label_value'). Supports regex (prefix with 'regex:'; e.g., 'regex:key=env')",
    )
    filter_args.add_argument(
        "--node-path",
        metavar="PATTERN",
        help="Filter by node path (folder structure: '/folder1/folder2'). Supports regex (prefix with 'regex:')",
    )

    filter_args.add_argument(
        "--version",
        metavar="PATTERN",
        help=(
            "Filter by software version (supports <, >, <=, >= operators and regex). "
            "Example: '>1.0.0' (newer than 1.0.0)"
        ),
    )


def args_ms_nodes_workload_filters(parser):
    filter_workload_group = parser.add_argument_group(
        "Filters based on nodes workload properties. Only nodes"
        " including the workloads matching the defined filters will be included in the output."
    )
    filter_workload_group.add_argument(
        "--workload-name",
        metavar="FILTER",
        help="Filter by workload name. Regex is supported with prefix 'regex:'.",
    )
    filter_workload_group.add_argument(
        "--workload-version-name",
        metavar="FILTER",
        help="Filter by workload version name. Regex is supported with prefix 'regex:'.",
    )
    filter_workload_group.add_argument(
        "--workload-status",
        help="Filter by workload status.",
        choices=[
            "IDLE",
            "CREATING",
            "REMOVING",
            "SUSPENDING",
            "SUSPENDED",
            "STARTING",
            "RESTARTING",
            "RESUMING",
            "STARTED",
            "STOPPING",
            "STOPPED",
            "ERROR",
            "REMOVING_FAILED",
            "PARTIALLY_RUNNING",
        ],
    )
    filter_workload_group.add_argument(
        "--workload-type",
        help="Filter by workload type.",
        choices=["docker", "codesys", "vm", "docker-compose"],
    )
    filter_workload_group.add_argument(
        "--remove-non-matching-workloads",
        help=(
            "If set, workloads not matching filters are removed from each node's workload list. "
            "Nodes matching node-level filters are still kept."
        ),
        action="store_true",
    )


def args_ms_nodes_remote_connection_filters(parser):
    filter_remote_connections_group = parser.add_argument_group(
        "Filter arguments for node remote connections. The defined filters are applied to each node's "
        "remote connections and only matching entries are kept."
    )
    filter_remote_connections_group.add_argument(
        "--remote-connection-type",
        help="Filter by remote connection type.",
        choices=["TUNNEL", "SCREEN"],
    )
    filter_remote_connections_group.add_argument(
        "--remote-connection-name",
        metavar="FILTER",
        help="Filter by remote connection name. Regex is supported with prefix 'regex:'.",
    )


def args_ms_nodes_list(parser):
    args_ms_node_filters(parser)
    args_ms_nodes_workload_filters(parser)
    args_ms_nodes_remote_connection_filters(parser)


def parse_semantic_version(version_str):
    """Parse a semantic version string (major.minor.patch) to a tuple of integers for comparison."""
    try:
        return tuple(int(part) for part in version_str.split("."))
    except (ValueError, AttributeError):
        return None


def find_path(data, node_name, path=None):
    if path is None:
        path = []

    if isinstance(data, dict):
        for key, value in data.items():
            new_path = [*path, key]
            if key == "name" and value == node_name:
                return path

            result = find_path(value, node_name, new_path)
            if result:
                return result
    elif isinstance(data, list):
        for index, item in enumerate(data):
            result = find_path(item, node_name, path)
            if result:
                return result

    return None


def _filter_name(name, args, log):
    if args.name.startswith("regex:"):
        pattern = args.name[len("regex:") :]
        return re.search(pattern, name) is not None
    return args.name == name


def _filter_serial_number(serial_number, args, log):
    if args.serial_number.startswith("regex:"):
        pattern = args.serial_number[len("regex:") :]
        return re.search(pattern, serial_number) is not None
    return args.serial_number == serial_number


def _filter_version(version, args, log):
    if args.version.startswith("regex:"):
        pattern = args.version[len("regex:") :]
        return re.search(pattern, version) is not None
    match = re.match(r"(<=|>=|<|>)(.+)", args.version)
    if match:
        op_str, ver_str = match.groups()
        ops = {
            "<": operator.lt,
            ">": operator.gt,
            "<=": operator.le,
            ">=": operator.ge,
        }
        op_func = ops[op_str]
        # Parse semantic versions for proper comparison
        version_tuple = parse_semantic_version(version)
        ver_str_tuple = parse_semantic_version(ver_str)
        if version_tuple is not None and ver_str_tuple is not None:
            return op_func(version_tuple, ver_str_tuple)
        # Fallback to string comparison if semantic parsing fails
        return op_func(version, ver_str)
    return args.version == version


def _filter_labels(node_labels, args, log):
    if not args.labels:
        return True
    label_filters = args.labels.split(",")
    for label_filter in label_filters:
        if label_filter.startswith("regex:"):
            pattern = label_filter[len("regex:") :]
            if any(re.search(pattern, f"key={label['key']}/value={label['value']}") for label in node_labels):
                continue
            return False
        key_value = label_filter.split("/")
        if len(key_value) != 2:  # noqa: PLR2004
            log.warning(
                "Invalid label filter format: %s. Expected 'key=label_key/value=label_value'. Skipping this filter.",
                label_filter,
            )
            continue
        key, value = key_value
        if not any(label["key"] == key and label["value"] == value for label in node_labels):
            return False
    return True


def _filter_path(node_path, args, log):
    if not args.node_path:
        return True
    if args.node_path.startswith("regex:"):
        pattern = args.node_path[len("regex:") :]
        return re.search(pattern, "/".join(node_path)) is not None
    return args.node_path == "/".join(node_path)


def _filter_workload(workload, args, log):
    def filter_workload_name(workload_name):
        if args.workload_name.startswith("regex:"):
            pattern = args.workload_name[len("regex:") :]
            return re.search(pattern, workload_name) is not None
        return args.workload_name == workload_name

    def filter_workload_version_name(workload_version_name):
        if args.workload_version_name.startswith("regex:"):
            pattern = args.workload_version_name[len("regex:") :]
            return re.search(pattern, workload_version_name) is not None
        return args.workload_version_name == workload_version_name

    def filter_workload_status(workload_status):
        return args.workload_status == workload_status

    def filter_workload_type(workload_type):
        return args.workload_type == workload_type

    if args.workload_name and not filter_workload_name(workload["name"]):
        return False
    if args.workload_version_name and not filter_workload_version_name(workload["version_name"]):
        return False
    if args.workload_status and not filter_workload_status(workload["state"]):
        return False
    if args.workload_type and not filter_workload_type(workload["type"]):  # noqa: SIM103
        return False
    return True


def _filter_remote_connection(remote_connection, args, log):
    if args.remote_connection_type and remote_connection["type"] != args.remote_connection_type:
        return False
    if args.remote_connection_name:
        if args.remote_connection_name.startswith("regex:"):
            pattern = args.remote_connection_name[len("regex:") :]
            return re.search(pattern, remote_connection["name"]) is not None
        return args.remote_connection_name == remote_connection["name"]
    return True


def filter_node(node, ms_nodes, args, log):
    """Apply filters for node level.

    Filters:
        --name
        --serial-number
        --online
        --model
        --version
    """
    if args.name and not _filter_name(node["name"], args, log):
        return False
    if args.serial_number and not _filter_serial_number(node["serialNumber"], args, log):
        return False
    if args.online and node["connectionStatus"] != "online":
        return False
    if args.version and not _filter_version(node["currentFWVersion"], args, log):
        return False

    if args.node_path and not _filter_path(node.get("path", []), args, log):
        # Only get node path if filter is defined
        node_paths = ms_nodes.node_tree._get_tree()
        node["path"] = find_path(node_paths, node["name"])
        return False

    return True


def filter_node_info(node, ms_nodes, args, log):
    """Apply filters for node-info level.

    Filters:
        --model
        --labels
        --workload-name
        --workload-version-name
        --workload-status
        --workload-type
        --remove-non-matching-workloads (affects output but not filtering itself)
    """
    # Extend node info with details
    required_keys = ["model", "labels", "workloads"]
    if not all(key in node for key in required_keys):
        node_info = ms_nodes.Node(node["serialNumber"])
        node_details = node_info.get_details()

        ## Model
        node["model"] = node_details.get("model", "unknown")
        ## Labels
        node["labels"] = []
        for label in node_details["labels"]:
            node["labels"].append({"key": label["key"], "value": label["value"]})
        # workloads
        node["workloads"] = []
        for wl in node_info.get_workloads() if node["connectionStatus"] == "online" else []:
            wl_service_control = next(
                wl_service for wl_service in wl["service_list"] if wl_service["name"] == "VMControlService"
            )
            wl_service_state = next(
                entry for entry in wl_service_control["property_list"] if entry["name"] == "State"
            )
            wl_state = wl_service_state["options"][wl_service_state["value"]]

            wl_service_conf = next(
                wl_service
                for wl_service in wl["service_list"]
                if wl_service["name"] == "WiseConfigurationService"
            )
            wl_conf_value = next(
                entry for entry in wl_service_conf["property_list"] if entry["name"] == "Value"
            )
            wl_version_name = json.loads(wl_conf_value["value"])["workloadVersionName"]

            node_wl = {
                "name": wl["device_name"],
                "type": wl["type"],
                "_id": wl["workloadId"],
                "version_id": wl["versionId"],
                "version_name": wl_version_name,
                "state": wl_state,
                "device_id": wl["id"],
            }

            node["workloads"].append(node_wl)

    if getattr(args, "model", None) and node["model"] != args.model:
        return False
    if getattr(args, "labels", None) and not _filter_labels(node.get("labels", []), args, log):
        return False

    if args.remove_non_matching_workloads:
        node["workloads"] = [wl for wl in node.get("workloads", []) if _filter_workload(wl, args, log)]

    if (  # noqa: SIM103
        args.workload_name or args.workload_version_name or args.workload_status or args.workload_type
    ) and not any(_filter_workload(wl, args, log) for wl in node.get("workloads", [])):
        return False

    return True


def filter_node_remote_connections(node, ms_nodes, args, log):
    """Apply filters for node remote connections.

    Filters:
        --remote-connection-type
        --remote-connection-name
    """
    # remote connections
    if "remote_connections" not in node:
        node["remote_connections"] = get_existing_remotes(ms_nodes, [node]).get(node["name"], [])

    node["remote_connections"] = [
        rc for rc in node["remote_connections"] if _filter_remote_connection(rc, args, log)
    ]

    # if filter for remote connection is defined, remove nodes without any match
    if (args.remote_connection_type or args.remote_connection_name) and not node["remote_connections"]:  # noqa: SIM103
        return False

    return True


def normalize_nodes_input(nodes, ms_nodes):
    """Normalize the node definitions by ensuring each node has both 'name' and 'serialNumber' keys."""
    normalize_nodes = []
    for node_item in nodes:
        if "serialNumber" not in node_item and "name" not in node_item:
            raise ValueError(
                f"Node item must contain either 'serialNumber' or 'name' key with valid value, got: {node_item.keys()}"
            )
        keys = ["_id", "name", "serialNumber", "labels", "workloads", "remote_connections"]
        if all(key in node_item for key in keys):
            normalize_nodes.append(node_item.copy())
            continue
        if "name" in node_item:
            node = next(
                (
                    node
                    for node in ms_nodes.get_nodes_filtered(node_name=node_item["name"])
                    if node["name"] == node_item["name"]
                ),
                None,
            )
            if not node:
                raise ValueError(f"Node with name '{node_item['name']}' not found on '{ms_nodes.ms.ms_url}'")
            normalize_nodes.append(node.copy())
            continue
        if "serialNumber" in node_item:
            node = next(
                (
                    node
                    for node in ms_nodes.get_nodes_filtered(serial_number=node_item["serialNumber"].upper())
                    if node["serialNumber"].upper() == node_item["serialNumber"].upper()
                ),
                None,
            )
            if not node:
                raise ValueError(
                    f"Node with serial number '{node_item['serialNumber']}' not found on '{ms_nodes.ms.ms_url}'"
                )
            normalize_nodes.append(node.copy())
            continue

    return normalize_nodes


def show_nodes(present_nodes, log):
    for node in present_nodes:
        workload_list = []
        for wl in node.get("workloads", []):
            workload_list.append(
                f"Name: {wl['name']:20}, Version: {wl['version_name']:20}, Status: {wl['state']}"
            )
        log.info(
            "Node '%s' (%s): \n    status   : %s\n    Workloads: - %s\n    Remote Connections: - %s",
            node["name"],
            node["serialNumber"],
            node["connectionStatus"],
            "\n               - ".join(workload_list),
            "\n                        - ".join([
                f"{rc['type']}: '{rc['name']}' ({rc['hostname']}:{rc['port']}->{rc.get('localPort', '')}{rc.get('connection', '')})"
                for rc in node.get("remote_connections", [])
            ]),
        )
