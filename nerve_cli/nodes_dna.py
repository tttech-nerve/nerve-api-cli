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


"""Function for dna file exchanges on nodes"""

import json
import logging
import os
import posixpath
from io import BytesIO
from zipfile import ZipFile

import requests
import yaml
from nerve_lib import MSDNA
from nerve_lib import CheckStatusCodeError

from .utils import args_interactive
from .utils import file_read
from .utils import file_write


def args_nodes_dna(parser):
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

    # optional args for get
    get_group = parser.add_argument_group("Get DNA configuration")
    get_group.add_argument(
        "-s", "--strip_hash", action="store_true", help="Strip the hash from the DNA configuration"
    )

    # optional args for deploy
    deploy_group = parser.add_argument_group("Deploy DNA configuration")
    deploy_group.add_argument(
        "-r",
        "--restart_all_workloads",
        action="store_true",
        help="Restart all workloads after deploying the DNA configuration",
    )
    deploy_group.add_argument(
        "-c",
        "--continue_after_restart",
        action="store_true",
        help="Continue DNA deployment in case node restarts",
    )

    commands_args = parser.add_mutually_exclusive_group(required=True)

    commands_args.add_argument(
        "--put_target",
        metavar="DNA_FILE",
        help="Deploy the DNA configuration to the nodes in 'file'. Multiple files (yaml + env files) can be provided by seperating them with a comma",
    )
    commands_args.add_argument(
        "--get_current",
        action="store_true",
        help="Get the current DNA configuration from the first node in 'file' (stored to 'dna-file')",
    )
    commands_args.add_argument(
        "--get_target",
        action="store_true",
        help="Get the target DNA configuration from the first node in 'file' (stored to 'dna-file')",
    )
    commands_args.add_argument(
        "--status", action="store_true", help="Get the DNA status of all nodes in 'file'"
    )


def strip_hash_from_dna_config(dna_config):
    for file in dna_config.values():
        for workload in file.get("workloads", []):
            workload.pop("hash", None)


def nodes_dna(ms_nodes, work_dir, arg, log=None):
    if not log:
        log = logging.getLogger(__name__)
    args = args_interactive(arg, args_nodes_dna, "DNA file exchange to nodes")
    if not args:
        return
    # Process the arguments as needed

    nodes = file_read(work_dir, args.file)
    for node in nodes:
        dna = MSDNA(ms_nodes.ms, node["serialNumber"])
        if args.get_current:
            dna_config = dna.get_current()
            if args.strip_hash:
                strip_hash_from_dna_config(dna_config)
            for file_name, content in dna_config.items():
                file_write(posixpath.join(work_dir, node["serialNumber"]), file_name, content)
            log.info(
                "Current DNA configuration of node %s:\n%s",
                node["name"],
                yaml.dump(dna_config, indent=4, default_flow_style=False),
            )
        if args.get_target:
            dna_config = dna.get_target()
            if args.strip_hash:
                strip_hash_from_dna_config(dna_config)
            for file_name, content in dna_config.items():
                file_write(posixpath.join(work_dir, node["serialNumber"]), file_name, content)
            log.info(
                "Target DNA configuration of node %s:\n%s",
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
            log.info("DNA status of node '%25s': %s", node["name"], dna_status)
        if args.put_target:
            zip_bin = BytesIO()
            with ZipFile(zip_bin, "w") as zip_object:
                for file_name in args.put_target.split(","):
                    file = file_read(work_dir, file_name)
                    if isinstance(file, dict):
                        file = yaml.dump(file, indent=4, default_flow_style=False)
                    zip_object.writestr(os.path.basename(file_name), file)

            dna.put_target(
                ("config.zip", zip_bin),
                continue_after_restart=args.continue_after_restart,
                restart_all_wl=args.restart_all_workloads,
            )
            log.info("DNA configuration deployed to node %s", node["name"])
