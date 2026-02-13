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


"""Function for listing and updating remote tunnels of a nodes"""

import json
import logging
import os
import subprocess
import webbrowser

from .utils import args_interactive
from .utils import file_read
from .utils import file_write


def args_nodes_remote_connections(parser):
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
        "-r",
        "--remotes_file",
        default="node_remotes.json",
        help="Filename or blank for 'node_remotes.json'. The '.json' ending is automatically appended if not provided.",
    )

    actions_group = parser.add_mutually_exclusive_group(required=True)
    actions_group.add_argument(
        "-t",
        "--template_create",
        help="Create a template file for remote tunnels. The template will be created for the type specified, or if 'first_node' is specified, the remoted from the first node in the list will be used for the template.",
        type=str,
        choices=["tunnel", "screen", "first_node"],
    )

    actions_group.add_argument(
        "-l",
        "--list",
        help="The tunnels/screens will be listed for the nodes in 'file'. The template file is not changed.",
        action="store_true",
    )

    actions_group.add_argument(
        "-a",
        "--add",
        help="The tunnels/screens will be added to the nodes in 'file' with the settings from the 'remotes_file'.",
        action="store_true",
    )

    actions_group.add_argument(
        "-d",
        "--delete",
        help="The tunnels/screens will be deleted from the nodes in 'file' with the settings from the 'remotes_file'.",
        action="store_true",
    )
    actions_group.add_argument(
        "-e", "--establish", help="Establish the remote connections.", action="store_true"
    )


def get_existing_remotes(ms_nodes, nodes):
    existing_remotes = {}
    for node in nodes:
        node_handle = ms_nodes.Node(node["serialNumber"])
        remotes = node_handle.get_remote_connections()
        for key in ["uniqueConnectionRequestNo", "workloadId", "versionId", "serialNumber"]:
            for remote in remotes:
                if key in remote:
                    del remote[key]
        if remotes:
            existing_remotes[node["name"]] = remotes
    return existing_remotes


def find_in_remotes_list(remote_element, remotes_list):
    if not remotes_list:
        return {}

    for remote_compare in remotes_list:
        result = True
        for key in remote_element:
            if key not in remote_compare:
                result = False
            elif remote_element[key] != remote_compare[key]:
                result = False
        if result:
            # One element in the list is equal to the element
            return remote_compare

    # No element in the list is equal to the element
    return {}


def nodes_remote_connections(ms_nodes, work_dir, arg, log=None):  # noqa: PLR0912
    if not log:
        log = logging.getLogger(__name__)
    args = args_interactive(
        arg,
        args_nodes_remote_connections,
        "Manage remote connections of a node. The node_remotes file will be updated or created if it does not exist.",
    )
    if not args:
        return
    # Process the arguments as needed

    if args.template_create:
        if args.template_create == "tunnel":
            file_write(
                work_dir,
                args.remotes_file,
                [
                    {
                        "hostname": "172.20.2.1",
                        "localPort": 3333,
                        "port": 3333,
                        "acknowledgment": "No",
                        "type": "TUNNEL",
                        "name": "LocalUi",
                    }
                ],
            )
        elif args.template_create == "screen":
            file_write(
                work_dir,
                args.remotes_file,
                [
                    {
                        "hostname": "172.20.2.20",
                        "securityMode": "any",
                        "ignoreServerCertificate": True,
                        "password": "",
                        "username": "admin",
                        "connection": "RDP",
                        "swapRedBlue": False,
                        "readOnly": False,
                        "cursor": "",
                        "autoretry": 1,
                        "numberOfConnections": 1,
                        "port": 3389,
                        "acknowledgment": "No",
                        "type": "SCREEN",
                        "name": "screen_test",
                    }
                ],
            )
        elif args.template_create == "first_node":
            nodes = file_read(work_dir, args.file)
            if not nodes:
                log.error("No nodes found in the file: %s", args.file)
                return
            node_handle = ms_nodes.Node(nodes[0]["serialNumber"])
            remotes = node_handle.get_remote_connections()
            for key in ["uniqueConnectionRequestNo", "workloadId", "versionId", "serialNumber", "_id"]:
                for remote in remotes:
                    if key in remote:
                        del remote[key]
            file_write(work_dir, args.remotes_file, remotes)

    if args.list:
        nodes = file_read(work_dir, args.file)
        existing_remotes = get_existing_remotes(ms_nodes, nodes)
        log.info("Remote connections for the nodes: \n%s", json.dumps(existing_remotes, indent=4))

    if args.add:
        nodes = file_read(work_dir, args.file)
        existing_remotes = get_existing_remotes(ms_nodes, nodes)

        file_remotes = file_read(work_dir, args.remotes_file)

        tunnels_to_add = {}
        for node in nodes:
            node_name = node["name"]
            if node_name not in existing_remotes:
                existing_remotes[node_name] = []

            for tunnel in file_remotes:
                if not find_in_remotes_list(tunnel, existing_remotes[node_name]):
                    if node_name not in tunnels_to_add:
                        tunnels_to_add[node_name] = []
                    tunnels_to_add[node_name].append(tunnel)
        log.info("Adding following remote_connections: \n%s", json.dumps(tunnels_to_add, indent=4))
        for node_name, remote_connection in tunnels_to_add.items():
            serial_number = next(node["serialNumber"] for node in nodes if node["name"] == node_name)
            node_handle = ms_nodes.Node(serial_number)
            node_handle.add_remote_connection(remote_connection)
    if args.delete:
        nodes = file_read(work_dir, args.file)
        existing_remotes = get_existing_remotes(ms_nodes, nodes)
        file_remotes = file_read(work_dir, args.remotes_file)

        tunnels_to_remove = {}
        for node in nodes:
            node_name = node["name"]
            if node_name not in existing_remotes:
                continue

            for tunnel in file_remotes:
                remote_element = find_in_remotes_list(tunnel, existing_remotes[node_name])
                if remote_element:
                    if node_name not in tunnels_to_remove:
                        tunnels_to_remove[node_name] = []
                    tunnels_to_remove[node_name].append(remote_element)
        log.info("Removing following remote connections: \n%s", json.dumps(tunnels_to_remove, indent=4))
        for node_name, remote_connection in tunnels_to_remove.items():
            serial_number = next(node["serialNumber"] for node in nodes if node["name"] == node_name)
            node_handle = ms_nodes.Node(serial_number)
            node_handle.remove_remote_connection(remote_connection)
    if args.establish:
        nodes = file_read(work_dir, args.file)
        remotes = file_read(work_dir, args.remotes_file)

        for node in nodes:
            existing_remotes = get_existing_remotes(ms_nodes, [node])
            if not existing_remotes:
                continue

            for remote in remotes:
                remote_element = find_in_remotes_list(remote, existing_remotes[node["name"]])

                if not remote_element:
                    continue

                log.info("Establishing remote connection for node %s: %s", node["name"], remote["name"])
                node_handle = ms_nodes.Node(node["serialNumber"])
                url = node_handle.get_remote_connections(remote["name"])

                # if os is linux use call "xdg-open" with url instead
                if os.name == "posix":
                    subprocess.call(["xdg-open", url])
                else:
                    webbrowser.open(url, new=0, autoraise=True)
