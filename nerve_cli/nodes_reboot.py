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


"""Function for rebooting nodes"""

import logging

import requests
from nerve_lib import CheckStatusCodeError

from .utils import args_interactive
from .utils import file_read


def args_nodes_reboot(parser):
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
    parser.add_argument("-y", "--yes", action="store_true", help="Don't ask for confirmation")


def nodes_reboot(ms_nodes, work_dir, arg, log=None):
    if not log:
        log = logging.getLogger(__name__)
    args = args_interactive(arg, args_nodes_reboot, "Reboot nodes")
    if not args:
        return
    # Process the arguments as needed

    nodes = file_read(work_dir, args.file)

    for node in nodes:
        # Ask for confirmation
        if not args.yes:
            response = input(f"Reboot node {node['name']}? (y/n): ")
            if response.lower() != "y":
                log.info("Skipping node %s", node["name"])
                continue

        log.info("Trigger command to reboot node %s", node["name"])
        node_handle = ms_nodes.Node(node["serialNumber"])
        try:
            node_handle.reboot()
        except CheckStatusCodeError as ex_msg:
            if ex_msg.status_code == requests.codes.conflict:
                log.warning("Node %s is currently offline and cannot be rebooted", node["name"])
