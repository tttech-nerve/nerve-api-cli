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


"""Function for changing the state of all deployed workloads."""

import logging

from .utils import args_interactive
from .utils import file_read


def args_nodes_workloads_state(parser):
    # mandatory args
    parser.add_argument(
        "-f",
        "--file",
        metavar="FILE_NAME",
        default="nodes.json",
        help=(
            "File containing the node list, 'nodes.json' if left unspecified. "
            " '.json' is added automatically if not specified"
        ),
    )

    parser.add_argument(
        "-s",
        "--state",
        help="Change the state of all workloads in the 'file'.",
        type=str,
        required=True,
        choices=["start", "stop", "restart", "pause", "resume", "suspend", "undeploy"],
    )


def nodes_workloads_state(ms_nodes, work_dir, arg, log=None):
    if not log:
        log = logging.getLogger(__name__)
    args = args_interactive(
        arg,
        args_nodes_workloads_state,
        "Change the state of all workloads in the nodes listed in the file.",
    )
    if not args:
        return
    # Process the arguments as needed

    nodes = file_read(work_dir, args.file)
    for node in nodes:
        node_handle = ms_nodes.Node(node["serialNumber"])
        for workload in node.get("workloads", []):
            workload_name = workload["name"]
            node_handle.workload_control(workload_name, args.state.upper())
