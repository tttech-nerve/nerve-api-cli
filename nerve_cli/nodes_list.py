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


"""Function for listing nodes"""

import json
import logging

from .utils import args_interactive
from .utils import check_filter_arg
from .utils import file_append
from .utils import file_write


def find_path(data, node_name, path=None):
    if path is None:
        path = []

    if isinstance(data, dict):
        for key, value in data.items():
            new_path = path + [key]
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


def args_nodes_list(parser):
    parser.add_argument(
        "-f",
        "--file",
        default="nodes.json",
        metavar="FILE_NAME",
        help=(
            "File where the node list will be stored in. Defaults to 'nodes.json' if left unspecified. "
            " '.json' is added automatically if not specified"
        ),
    )
    parser.add_argument(
        "-a", "--add", help="Add to the 'file' instead creating a new one.", action="store_true"
    )
    filter_node_group = parser.add_argument_group("Filters based on node properties")
    filter_node_group.add_argument(
        "-nc", "--node_connected", help="Filter by node connection status online", action="store_true"
    )
    filter_node_group.add_argument(
        "-nn",
        "--node_name",
        metavar="FILTER",
        help="Filter by node name, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_node_group.add_argument(
        "-np",
        "--node_path",
        metavar="FILTER",
        help=(
            "Filter by node path, supports regex (define 'regex:' followed by the filter-string). The path contains the folder names separated with '/'"
        ),
    )
    filter_node_group.add_argument(
        "-nv",
        "--node_version",
        metavar="FILTER",
        help="Filter by node version, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_node_group.add_argument(
        "-nm",
        "--node_model",
        metavar="FILTER",
        help="Filter by node model, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_node_group.add_argument(
        "-nl",
        "--node_labels",
        metavar="FILTER",
        help="Filter by node labels, supports regex (define 'regex:' followed by the filter-string). Labels will be checked as 'key=label_key/value=label_value'. To filter for a specific label use e.g. 'regex:key=label_key' as argument. Multiple labels are seperated by comma (',').",
    )
    filter_workload_group = parser.add_argument_group("Filters based on nodes workload properties")
    filter_workload_group.add_argument(
        "-wn",
        "--workload_name",
        metavar="FILTER",
        help="Filter by workload name, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_workload_group.add_argument(
        "-wid",
        "--workload_id",
        metavar="FILTER",
        help="Filter by workload ID, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_workload_group.add_argument(
        "-wvn",
        "--workload_version_name",
        metavar="FILTER",
        help="Filter by workload version name, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_workload_group.add_argument(
        "-wvid",
        "--workload_version_id",
        metavar="FILTER",
        help="Filter by workload version ID, supports regex (define 'regex:' followed by the filter-string).",
    )
    filter_workload_group.add_argument(
        "-ws",
        "--workload_status",
        help="Filter by workload status",
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
        "-wt",
        "--workload_type",
        help="Filter by workload type.",
        choices=["docker", "codesys", "vm", "docker-compose"],
    )


def nodes_list(ms_nodes, work_dir, arg, log=None):  # noqa: PLR0914
    if not log:
        log = logging.getLogger(__name__)
    args = args_interactive(arg, args_nodes_list, "List nodes and create a node list or add to the list")
    if not args:
        return

    # Process the arguments as needed
    output = []
    nodes = ms_nodes.get_nodes()

    node_pathes = ms_nodes.node_tree._get_tree()
    for node in nodes:
        if not check_filter_arg(args.node_name, node["name"]):
            continue

        if not check_filter_arg(args.node_version, node["currentFWVersion"]):
            continue

        node_info = ms_nodes.Node(node["serialNumber"])
        node_details = node_info.get_details()

        node["model"] = node_details.get("model", "N/A")
        if not check_filter_arg(args.node_model, node["model"]):
            continue

        node["labels"] = []
        check_label_filter = []
        for label in node_details["labels"]:
            node["labels"].append({"key": label["key"], "value": label["value"]})
            check_label_filter.append(f"key={label['key']}/value={label['value']}")

        if not check_filter_arg(args.node_labels, ",".join(check_label_filter)):
            continue

        node["path"] = find_path(node_pathes, node["name"])

        if not check_filter_arg(args.node_path, "/".join(node["path"])):
            continue

        workload_list = []
        if args.node_connected and node["connectionStatus"] != "online":
            continue

        if node["connectionStatus"] == "online":
            node["workloads"] = []
            for wl in node_info.get_workloads():
                if not check_filter_arg(args.workload_name, wl["device_name"]):
                    continue

                if not check_filter_arg(args.workload_id, wl["workloadId"]):
                    continue

                if not check_filter_arg(args.workload_version_id, wl["versionId"]):
                    continue

                if not check_filter_arg(args.workload_type, wl["type"]):
                    continue

                wl_service_control = next(
                    wl_service
                    for wl_service in wl["service_list"]
                    if wl_service["name"] == "VMControlService"
                )
                wl_service_state = next(
                    entry for entry in wl_service_control["property_list"] if entry["name"] == "State"
                )
                wl_state = wl_service_state["options"][wl_service_state["value"]]
                if not check_filter_arg(args.workload_status, wl_state):
                    continue

                wl_service_conf = next(
                    wl_service
                    for wl_service in wl["service_list"]
                    if wl_service["name"] == "WiseConfigurationService"
                )
                wl_conf_value = next(
                    entry for entry in wl_service_conf["property_list"] if entry["name"] == "Value"
                )
                wl_version_name = json.loads(wl_conf_value["value"])["workloadVersionName"]
                if not check_filter_arg(args.workload_version_name, wl_version_name):
                    continue

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
                workload_list.append(
                    f"Name: {node_wl['name']:20}, Version: {node_wl['version_name']:20}, Status: {wl_state}"
                )
        if (
            args.workload_name  # noqa: PLR0916
            or args.workload_id
            or args.workload_version_id
            or args.workload_type
            or args.workload_status
            or args.workload_version_name
        ):
            if node["connectionStatus"] != "online":
                continue
            if not workload_list:
                continue

        # Print Log output

        log.info(
            "Node '%s' (%s): \n    status   : %s\n    Path     : %s\n    Workloads: - %s",
            node["name"],
            node["serialNumber"],
            node["connectionStatus"],
            "/".join(node["path"]),
            "\n               - ".join(workload_list),
        )

        output.append(node)
    if args.add:
        file_append(work_dir, args.file, output)
    else:
        file_write(work_dir, args.file, output)
