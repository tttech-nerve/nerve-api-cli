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

import logging

import requests
from nerve_lib import CheckStatusCodeError
from nerve_lib import DockerVolumes

from .ms_nodes_dna import args_ms_nodes_dna
from .ms_nodes_dna import ms_nodes_dna
from .ms_nodes_remote_connections import args_nodes_remote_connections
from .ms_nodes_remote_connections import nodes_remote_connections
from .utils import args_interactive
from .utils import ask_for_confirmation
from .utils import file_read
from .utils import file_write
from .utils_docker_volumes import args_docker_volumes
from .utils_docker_volumes import docker_volumes
from .utils_nodes import args_ms_node_filters
from .utils_nodes import args_ms_nodes_list
from .utils_nodes import args_ms_nodes_remote_connection_filters
from .utils_nodes import args_ms_nodes_workload_filters
from .utils_nodes import filter_node
from .utils_nodes import filter_node_info
from .utils_nodes import filter_node_remote_connections
from .utils_nodes import normalize_nodes_input
from .utils_nodes import show_nodes


def _add_ms_nodes_input_argument(parser):
    parser.add_argument(
        "--input",
        metavar="SOURCE",
        default="nodes.json",
        help="Input source for nodes: FILE path (e.g., 'nodes.json'), stdin:json, stdin:yaml, name:node1,node2, or serialNumber:serial1, default is 'nodes.json'",
    )


def _add_ms_nodes_output_argument(parser, default="nodes.json"):
    help_text = f"Output destination: FILE path (e.g., 'output.json'), stdout:json, stdout:yaml, or stdout:key (e.g., stdout:name), default is '{default}'"
    if default != "nodes.json":
        help_text += f"Output destination: FILE path (e.g., 'output.json'), stdout:json or stdout:yaml, default is '{default}'"
    parser.add_argument(
        "--output",
        metavar="DESTINATION",
        default=default,
        help=help_text,
    )


def _ms_nodes_action_parser(action_parser, action_name, help_text):
    parser = action_parser.add_parser(action_name, help=help_text)
    parser.set_defaults(ms_nodes_action=action_name)
    return parser


def args_ms_nodes(parser):
    action_parser = parser.add_subparsers(
        dest="ms_nodes_action", required=True, help="Available ms-nodes actions"
    )

    list_parser = _ms_nodes_action_parser(
        action_parser,
        "list",
        "List nodes from Management System and save matching results to OUTPUT.",
    )
    _add_ms_nodes_output_argument(list_parser)
    args_ms_nodes_list(list_parser)

    workload_state_parser = _ms_nodes_action_parser(
        action_parser,
        "set-workload-state",
        "Set workload state on nodes from INPUT using workload-related filters.",
    )
    _add_ms_nodes_input_argument(workload_state_parser)
    workload_state_parser.add_argument(
        "state",
        metavar="STATE",
        choices=["START", "STOP", "RESTART", "PAUSE", "RESUME", "SUSPEND", "UNDEPLOY"],
        help=(
            "Set workload state on nodes from INPUT. Possible states: START, STOP, RESTART, PAUSE, RESUME, SUSPEND, UNDEPLOY"
        ),
    )
    args_ms_nodes_workload_filters(workload_state_parser)

    reboot_parser = _ms_nodes_action_parser(action_parser, "reboot", "Reboot all nodes from INPUT.")
    _add_ms_nodes_input_argument(reboot_parser)

    node_dna_parser = _ms_nodes_action_parser(
        action_parser,
        "node-dna",
        "Manage node DNA configuration on nodes from INPUT using DNA command options.",
    )
    _add_ms_nodes_input_argument(node_dna_parser)
    _add_ms_nodes_output_argument(node_dna_parser, default="node_dna_status.json")
    args_ms_nodes_dna(node_dna_parser)
    node_dna_parser.set_defaults(node_dna=True, workload_dna=False)

    workload_dna_parser = _ms_nodes_action_parser(
        action_parser,
        "workload-dna",
        "Manage workload DNA configuration on nodes from INPUT using DNA command options.",
    )
    _add_ms_nodes_input_argument(workload_dna_parser)
    _add_ms_nodes_output_argument(workload_dna_parser, default="workload_dna_status.json")
    args_ms_nodes_dna(workload_dna_parser)
    workload_dna_parser.set_defaults(node_dna=False, workload_dna=True)

    remote_connections_parser = _ms_nodes_action_parser(
        action_parser,
        "remote-connections",
        "(experimental) Manage remote tunnel and screen connections for nodes from INPUT.",
    )
    _add_ms_nodes_input_argument(remote_connections_parser)
    _add_ms_nodes_output_argument(remote_connections_parser, default="remote_connections.json")
    args_nodes_remote_connections(remote_connections_parser)
    args_ms_node_filters(remote_connections_parser)
    args_ms_nodes_remote_connection_filters(remote_connections_parser)

    docker_volumes_parser = _ms_nodes_action_parser(
        action_parser,
        "docker-volumes",
        "Manage Docker volumes on nodes from INPUT using Docker volume options.",
    )
    _add_ms_nodes_input_argument(docker_volumes_parser)
    args_docker_volumes(docker_volumes_parser)


def _get_ms_nodes_action(args):
    return getattr(args, "ms_nodes_action", "")


def ms_nodes(parent, arg, log=None):  # noqa: PLR0911
    log = log.getChild(__name__.split(".")[-1]) if log else logging.getLogger(__name__)

    args = args_interactive(arg, args_ms_nodes, "List nodes and create a node list or add to the list")
    if not args:
        return 2

    ms_nodes = parent.ms_nodes
    args.work_dir = parent.args.work_dir
    args.dry_run = parent.args.dry_run
    args.yes = parent.args.yes
    action = _get_ms_nodes_action(args)

    if action == "list":
        nodes = ms_nodes.get_nodes()
        log.info("%d Nodes found on MS, reading details and applying filters now...", len(nodes))
        # filter in steps
        nodes = list(filter(lambda node: filter_node(node, ms_nodes, args, log), nodes))
        log.info("%d Nodes matched node filters and are included in the output", len(nodes))

        nodes = list(filter(lambda node: filter_node_info(node, ms_nodes, args, log), nodes))
        log.info("%d Nodes matched node info filters (and are included in the output", len(nodes))

        nodes = list(filter(lambda node: filter_node_remote_connections(node, ms_nodes, args, log), nodes))
        log.info("%d Nodes matched remote connection filters and are included in the output", len(nodes))

        show_nodes(nodes, log)

        file_write(args.work_dir, args.output, nodes, output_methods=["stdout", "key", "file"])
        return 0

    nodes = normalize_nodes_input(
        file_read(args.work_dir, args.input, input_methods=["stdin", "name", "serialNumber", "_id", "file"]),
        ms_nodes,
    )

    if action == "reboot":
        ret_val = 0
        perform_action = ask_for_confirmation(
            args, f"Are you sure you want to reboot the nodes '{','.join(node['name'] for node in nodes)}'?"
        )
        for node in nodes:
            if not perform_action:
                log.info("Skipping reboot of node %s", node["name"])
                continue
            log.info("Trigger command to reboot node %s", node["name"])
            node_handle = ms_nodes.Node(node["serialNumber"])
            try:
                node_handle.reboot()
            except CheckStatusCodeError as ex_msg:
                if ex_msg.status_code == requests.codes.conflict:
                    log.warning("Node %s is currently not reachable and cannot be rebooted", node["name"])
                    ret_val = 1

        return ret_val

    if action in {"node-dna", "workload-dna"}:
        return ms_nodes_dna(ms_nodes, nodes, args, log)

    if action == "docker-volumes":
        ms_volumes = DockerVolumes(ms_nodes.ms)
        return docker_volumes([node["serialNumber"] for node in nodes], args, ms_volumes, log)

    if action == "set-workload-state":
        # Apply workload filters
        args.remove_non_matching_workloads = True
        nodes = list(filter(lambda node: filter_node_info(node, ms_nodes, args, log), nodes))
        if not nodes:
            log.info(
                "No nodes have workloads matching the specified filters. No workload state changes will be made."
            )
            return 1

        perform_action = ask_for_confirmation(
            args,
            f"Are you sure you want to change the state of the workloads on the nodes '{','.join(node['name'] for node in nodes)}' to '{args.state.upper()}'?",
        )
        for node in nodes:
            node_handle = ms_nodes.Node(node["serialNumber"])
            for workload in node.get("workloads", []):
                workload_name = workload["name"]
                if not perform_action:
                    log.info(
                        "Skipping changing state of workload %s on node %s",
                        workload_name,
                        node["name"],
                    )
                    continue
                node_handle.workload_control(workload_name, args.state.upper())
        return 0

    if action == "remote-connections":
        # Apply remote-connection filters
        nodes = list(filter(lambda node: filter_node_remote_connections(node, ms_nodes, args, log), nodes))
        if not nodes:
            log.info(
                "No nodes have remote connections matching the specified filters. No remote connection actions will be made."
            )
            return 1
        return nodes_remote_connections(ms_nodes, nodes, args, log)

    return 1
