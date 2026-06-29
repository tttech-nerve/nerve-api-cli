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
import os
from io import BytesIO
from zipfile import ZipFile
from zipfile import is_zipfile

import requests
import yaml
from nerve_lib import MSDNA
from nerve_lib import CheckStatusCodeError
from nerve_lib import ServiceOSDNA

from .utils import ask_for_confirmation
from .utils import file_read
from .utils import file_write


def args_ms_nodes_dna(parser):
    dna_command_args_group = parser.add_argument_group(
        "Mutually exclusive arguments for node-dna and workload-dna actions"
    )
    dna_command_args = dna_command_args_group.add_mutually_exclusive_group()
    dna_command_args.add_argument(
        "--put-target",
        metavar="DNA_FILE",
        help=(
            "Deploy DNA configuration from FILE to nodes (absolute FILE path supported; "
            "e.g., '/tmp/config.yaml', 'dna_config.json')"
        ),
    )
    dna_command_args.add_argument(
        "--get-current",
        metavar="PATH",
        help=(
            "Download current DNA configuration to PATH/NODE_SERIAL/current_<dna_type>.json "
            "(absolute PATH supported)"
        ),
    )
    dna_command_args.add_argument(
        "--get-target",
        metavar="PATH",
        help=(
            "Download target DNA configuration to PATH/NODE_SERIAL/target_<dna_type>.json "
            "(absolute PATH supported)"
        ),
    )
    dna_command_args.add_argument(
        "--status", action="store_true", help="Display DNA deployment status for all nodes"
    )
    dna_command_args.add_argument(
        "--cancel",
        action="store_true",
        help="Cancel ongoing DNA deployment on all nodes",
    )
    dna_command_args.add_argument(
        "--re-apply",
        action="store_true",
        help="Re-apply target DNA configuration to all nodes",
    )

    optional_dna_args = parser.add_argument_group("Optional arguments for workload-dna actions")
    optional_dna_args.add_argument(
        "--strip-hash",
        action="store_true",
        help="Remove hash values from DNA configuration",
    )
    optional_dna_args.add_argument(
        "--restart-all-workloads",
        action="store_true",
        help="Restart all workloads after DNA deployment",
    )
    optional_dna_args.add_argument(
        "--continue-after-restart",
        action="store_true",
        help="Continue DNA deployment if node restarts during process",
    )
    optional_dna_args.add_argument(
        "--remove-docker-images",
        action="store_true",
        help="Remove unused Docker images before DNA deployment",
    )


def ms_nodes_dna(ms_nodes, nodes, args, log):
    dna_type = "workload-dna" if args.workload_dna else "node-dna"

    def strip_hash_from_dna_config(dna_config):
        for file in dna_config.values():
            for workload in file.get("workloads", []):
                workload.pop("hash", None)

    if not (
        args.status or args.get_current or args.get_target or args.put_target or args.cancel or args.re_apply
    ):
        log.error(
            "No node/workload-dna command argument specified,"
            " please provide one of --status, --get-current, --get-target, --put-target, --cancel or --re-apply"
        )
        return 2

    action_str = (
        f"deploy the target {dna_type} configuration from '{args.put_target}' to"
        if args.put_target
        else f"cancel the target {dna_type} deployment"
        if args.cancel
        else f"re-apply the target {dna_type} configuration"
        if args.re_apply
        else ""
    )
    if action_str:
        perform_action = ask_for_confirmation(
            args, f"Are you sure you want to {action_str} on '{', '.join(node['name'] for node in nodes)}'?"
        )
    status_nodes = {}
    for node in nodes:  # noqa: PLR1702
        if args.node_dna:
            dna = ServiceOSDNA(ms_nodes.ms, node["serialNumber"])
        else:
            dna = MSDNA(ms_nodes.ms, node["serialNumber"])
        if args.get_current:
            dna_config = dna.get_current()
            if args.strip_hash and args.workload_dna:
                strip_hash_from_dna_config(dna_config)
            if args.workload_dna:
                os.makedirs(
                    os.path.join(args.work_dir, args.get_current, node["serialNumber"]), exist_ok=True
                )
                with ZipFile(
                    os.path.join(
                        args.work_dir, args.get_current, node["serialNumber"], f"current_{dna_type}.zip"
                    ),
                    "w",
                ) as zip_object:
                    for file_name, file_content in dna_config.items():
                        if file_name.endswith((".yaml", ".yml")):
                            zip_object.writestr(
                                os.path.basename(file_name),
                                yaml.dump(file_content, indent=4, default_flow_style=False),
                            )
                        else:
                            zip_object.writestr(os.path.basename(file_name), file_content)
            else:
                file_write(
                    os.path.join(os.path.join(args.work_dir, args.get_current), node["serialNumber"]),
                    f"current_{dna_type}.yaml",
                    dna_config,
                )
            log.info(
                "Current %s configuration of node '%s':\n%s",
                dna_type,
                node["name"],
                yaml.dump(dna_config, indent=4, default_flow_style=False),
            )
        if args.get_target:
            dna_config = dna.get_target()
            if args.strip_hash and args.workload_dna:
                strip_hash_from_dna_config(dna_config)
            if args.workload_dna:
                os.makedirs(os.path.join(args.work_dir, args.get_target, node["serialNumber"]), exist_ok=True)
                with ZipFile(
                    os.path.join(
                        args.work_dir, args.get_target, node["serialNumber"], f"target_{dna_type}.zip"
                    ),
                    "w",
                ) as zip_object:
                    for file_name, file_content in dna_config.items():
                        if file_name.endswith((".yaml", ".yml")):
                            zip_object.writestr(
                                os.path.basename(file_name),
                                yaml.dump(file_content, indent=4, default_flow_style=False),
                            )
                        else:
                            zip_object.writestr(os.path.basename(file_name), file_content)
            else:
                file_write(
                    os.path.join(os.path.join(args.work_dir, args.get_target), node["serialNumber"]),
                    f"target_{dna_type}.yaml",
                    dna_config,
                )
            log.info(
                "Target %s configuration of node '%s':\n%s",
                dna_type,
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
            log.info("%s status of node %25s: %s", dna_type, node["name"], dna_status)
            status_nodes[node["name"]] = dna_status

        if (args.put_target or args.cancel or args.re_apply) and not perform_action:
            log.info("Skipping %s node '%s'", action_str, node["name"])
            continue
        if args.put_target:
            if args.node_dna:
                file = file_read(args.work_dir, args.put_target, input_methods=["file"])
                if file:
                    dna.put_target(file)
            else:
                files = [f.strip() for f in args.put_target.split(",")]
                if len(files) == 1 and is_zipfile(os.path.join(args.work_dir, files[0])):
                    with open(os.path.join(args.work_dir, files[0]), "rb") as f:
                        zip_bin = BytesIO(f.read())
                else:
                    zip_bin = BytesIO()
                    with ZipFile(zip_bin, "w") as zip_object:
                        for file_name in files:
                            file = file_read(args.work_dir, file_name)
                            if isinstance(file, dict):
                                file = yaml.dump(file, indent=4, default_flow_style=False)
                            zip_object.writestr(os.path.basename(file_name), file)

                dna.put_target(
                    ("config.zip", zip_bin),
                    continue_after_restart=args.continue_after_restart,
                    restart_all_wl=args.restart_all_workloads,
                    remove_images=args.remove_docker_images,
                )
            log.info("%s configuration deployed to node '%s'", dna_type, node["name"])
        if args.cancel:
            dna.cancel_target()
            log.info("%s target deployment cancelled on node '%s'", dna_type, node["name"])
        if args.re_apply:
            dna.reapply_target()
            log.info("%s target re-apply triggered on node '%s'", dna_type, node["name"])

    if args.status:
        file_write(args.work_dir, args.output, status_nodes, output_methods=["stdout", "file"])

    return 0
