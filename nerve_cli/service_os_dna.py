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


"""Function for service OS DNA file exchanges to nodes"""

import json
import logging
import posixpath

import requests
import yaml
from nerve_lib import CheckStatusCodeError
from nerve_lib import ServiceOSDNA

from .utils import args_interactive
from .utils import file_read
from .utils import file_write


def args_service_os_dna(parser):
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

    commands_args = parser.add_mutually_exclusive_group(required=True)

    commands_args.add_argument(
        "--put_target",
        metavar="DNA_FILE",
        help="Deploy the ServiceOS DNA configuration to the nodes in 'file'. One yaml/json file must be provided.",
    )
    commands_args.add_argument(
        "--get_current",
        action="store_true",
        help="Get the current ServiceOS DNA configuration from all nodes in 'file' (stored to '<node_serial>/current_service_os_dna.json')",
    )
    commands_args.add_argument(
        "--get_target",
        action="store_true",
        help="Get the target ServiceOS DNA configuration from all nodes in 'file' (stored to '<node_serial>/target_service_os_dna.json')",
    )
    commands_args.add_argument(
        "--status", action="store_true", help="Get the ServiceOS DNA status of all nodes in 'file'"
    )
    commands_args.add_argument(
        "--cancel",
        action="store_true",
        help="Cancel the ServiceOS DNA target deployment on the nodes in 'file'",
    )
    commands_args.add_argument(
        "--re-apply",
        action="store_true",
        help="Re-apply the target ServiceOS DNA configuration on the nodes in 'file'",
    )


def service_os_dna(ms_nodes, work_dir, arg, log=None):
    if not log:
        log = logging.getLogger(__name__)
    args = args_interactive(arg, args_service_os_dna, "ServiceOS DNA file exchange to nodes")
    if not args:
        return
    # Process the arguments as needed

    nodes = file_read(work_dir, args.file)
    for node in nodes:
        dna = ServiceOSDNA(ms_nodes.ms, node["serialNumber"])
        if args.get_current:
            dna_config = dna.get_current()
            file_write(
                posixpath.join(work_dir, node["serialNumber"]), "current_service_os_dna.json", dna_config
            )
            log.info(
                "Current ServiceOS DNA configuration of node %s:\n%s",
                node["name"],
                yaml.dump(dna_config, indent=4, default_flow_style=False),
            )
        if args.get_target:
            dna_config = dna.get_target()
            file_write(
                posixpath.join(work_dir, node["serialNumber"]), "target_service_os_dna.json", dna_config
            )
            log.info(
                "Target ServiceOS DNA configuration of node %s:\n%s",
                node["name"],
                yaml.dump(dna_config, indent=4, default_flow_style=False),
            )
        if args.status:
            try:
                dna_status = dna.get_status()
            except CheckStatusCodeError as ex_msg:
                if ex_msg.status_code == requests.codes.not_found:
                    dna_status = json.loads(ex_msg.response_text)[0].get("message")
                else:
                    dna_status = ex_msg.response_text
            log.info("ServiceOS DNA status of node '%25s': %s", node["name"], dna_status)
        if args.put_target:
            file = file_read(work_dir, args.put_target)
            if file:
                dna.put_target(file)
            log.info("ServiceOS DNA configuration deployed to node %s", node["name"])
        if args.cancel:
            dna.cancel_target()
            log.info("ServiceOS DNA target deployment cancelled on node %s", node["name"])
        if args.re_apply:
            dna.reapply_target()
            log.info("ServiceOS DNA target re-apply triggered on node %s", node["name"])
