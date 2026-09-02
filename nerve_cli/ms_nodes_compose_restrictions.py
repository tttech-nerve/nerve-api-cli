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

"""Function for managing compose-restrictions.json of nodes"""

import os

from .utils import ask_for_confirmation
from .utils import file_read
from .utils import file_write


def args_ms_nodes_compose_restrictions(parser):
    action_parser = parser.add_subparsers(
        dest="compose_restrictions_action", required=True, help="Available compose-restrictions actions"
    )

    get_parser = action_parser.add_parser(
        "get", help="Get the compose-restrictions.json file from nodes and save it to PATH."
    )
    get_parser.add_argument(
        "path",
        metavar="PATH",
        help=(
            "Directory to store compose restrictions files, one file per node named"
            " 'compose-restrictions-<serial-number>.json'."
        ),
    )
    get_parser.add_argument(
        "--default",
        action="store_true",
        help=(
            "Get the default compose-restrictions.json file instead of the active one. The default file is"
            " the one that is used when no active compose-restrictions.json file is present on the node."
        ),
    )

    version_parser = action_parser.add_parser(
        "version",
        help="Get the active compose-restrictions.json version from nodes and save it to PATH.",
    )
    version_parser.add_argument(
        "path",
        metavar="PATH",
        help=(
            "Directory to store compose restrictions version files, one file per node named"
            " 'compose-restrictions-version-<serial-number>.json'."
        ),
    )

    update_parser = action_parser.add_parser(
        "update",
        help="Update the compose-restrictions.json file on nodes using content from FILE.",
    )
    update_parser.add_argument(
        "file",
        metavar="FILE",
        help=(
            "FILE path to the new compose restrictions content (JSON). The 'version' field in FILE must"
            " match the version of the currently active compose-restrictions.json file on the node, unless"
            " --base-version or --force is used. The node automatically increments the version on update."
        ),
    )
    update_parser.add_argument(
        "--base-version",
        metavar="VERSION",
        type=int,
        default=0,
        help="Version of the active compose-restrictions.json file the update from FILE is based on.",
    )
    update_parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Read the currently active compose-restrictions.json version from each node first and use it"
            " as base version instead of the version in FILE or --base-version."
        ),
    )


def ms_nodes_compose_restrictions(ms_nodes, nodes, args, log):
    action = args.compose_restrictions_action

    if action == "get":
        for node in nodes:
            node_handle = ms_nodes.Node(node["serialNumber"])
            content = node_handle.get_compose_restrictions(source="default" if args.default else "active")
            file_write(
                args.work_dir,
                os.path.join(args.path, f"compose-restrictions-{node_handle.serial_number}.json"),
                content,
            )
        return 0

    if action == "version":
        for node in nodes:
            node_handle = ms_nodes.Node(node["serialNumber"])
            content = node_handle.get_compose_restrictions_version()
            file_write(
                args.work_dir,
                os.path.join(args.path, f"compose-restrictions-version-{node_handle.serial_number}.json"),
                content,
            )
        return 0

    if action == "update":
        content = file_read(args.work_dir, args.file)
        perform_action = ask_for_confirmation(
            args,
            f"Are you sure you want to update the compose restrictions on the nodes '{', '.join(node['name'] for node in nodes)}'?",
        )
        for node in nodes:
            node_handle = ms_nodes.Node(node["serialNumber"])
            if not perform_action:
                log.info("Skipping updating compose restrictions on node '%s'", node["name"])
                continue
            base_version = args.base_version
            if args.force:
                base_version = node_handle.get_compose_restrictions_version().get("version", base_version)
            node_handle.update_compose_restrictions(content, base_version)
            log.info(
                "Updated compose restrictions on node '%s' based on version '%s'", node["name"], base_version
            )
        return 0

    return 1
