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


"""Function for listing and updating remote tunnels of a nodes"""

import os
import subprocess
import time
import webbrowser

from nerve_lib import MSUser

from .utils import ask_for_confirmation
from .utils import file_read
from .utils import file_write


def args_nodes_remote_connections(parser):
    remote_connection_group = parser.add_argument_group("Arguments for remote connection")
    actions_group = remote_connection_group.add_mutually_exclusive_group(required=False)

    actions_group.add_argument(
        "--add",
        metavar="SOURCE",
        help="Add remote connections (tunnels/screens) to nodes. SOURCE: FILE path, stdin:json, or stdin:yaml",
    )

    actions_group.add_argument(
        "--delete",
        action="store_true",
        help="Delete remote connections (tunnels/screens) from nodes.",
    )
    actions_group.add_argument(
        "--url",
        help="Generate remote connection URLs for nodes. Output format: JSON with 'node-name' and 'urls' fields",
        action="store_true",
    )
    actions_group.add_argument(
        "--establish",
        help=(
            "Open remote connection URLs using Nerve Connection Manager."
            " Requires installation of 'nerve-connection-manager'. "
            " Requires installation of 'wslu' package on WSL."
        ),
        action="store_true",
    )
    actions_group.add_argument(
        "--prune-remote-connections",
        help="Remove all remote connections from Management System for current user",
        action="store_true",
    )


def get_existing_remotes(ms_nodes, nodes):
    existing_remotes = {}
    for node in nodes:
        node_handle = ms_nodes.Node(node["serialNumber"])
        remotes = node_handle.get_remote_connections()
        for key in ["uniqueConnectionRequestNo", "workloadId", "versionId", "serialNumber"]:
            for remote in remotes:
                remote.pop(key, None)
        if remotes:
            existing_remotes[node["name"]] = remotes
    return existing_remotes


def find_in_remotes_list(remote_element, remotes_list):
    if not remotes_list:
        return {}

    for remote_compare in remotes_list:
        result = True
        for key in remote_element:
            if key not in remote_compare or remote_element[key] != remote_compare[key]:
                result = False
        if result:
            # One element in the list is equal to the element
            return remote_compare

    # No element in the list is equal to the element
    return {}


def nodes_remote_connections(ms_nodes, nodes, args, log):  # noqa: PLR0912, PLR0914, PLR0915
    if args.add:
        if args.input.startswith("stdin:") and args.add.startswith("stdin:"):
            log.error(
                "Both 'input' and 'add' arguments cannot be read from standard input. Please provide at least one of them as a file."
            )
            return 2
        existing_remotes = get_existing_remotes(ms_nodes, nodes)
        file_remotes = file_read(args.work_dir, args.add, input_methods=["stdin", "file"])

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
        add_info_str = ""
        for node_name, remote_connection in tunnels_to_add.items():
            add_info_str = f"Node: '{node_name}'\n"
            for rc in remote_connection:
                add_info_str += f"\t- {rc['type']}: '{rc['name']}' ({rc['hostname']}:{rc['port']}->{rc.get('localPort', '')}{rc.get('connection', '')})\n"
            existing_remotes[node_name].extend(remote_connection)
        perform_action = ask_for_confirmation(
            args, f"Are you sure you want to add the following remote connections?\n{add_info_str}"
        )
        for node_name, remote_connection in tunnels_to_add.items():
            serial_number = next(node["serialNumber"] for node in nodes if node["name"] == node_name)
            node_handle = ms_nodes.Node(serial_number)
            if perform_action:
                node_handle.add_remote_connection(remote_connection)
            else:
                log.info(
                    "Skipping adding remote connection %s to node %s", remote_connection["name"], node_name
                )
    if args.delete:
        tunnels_to_remove = {}
        for node in nodes:
            node_name = node["name"]
            remotes = node["remote_connections"]
            for remote_element in remotes:
                if node_name not in tunnels_to_remove:
                    tunnels_to_remove[node_name] = []
                tunnels_to_remove[node_name].append(remote_element)

        remote_info_str = ""
        for node_name, remote_connection in tunnels_to_remove.items():
            remote_info_str += f"Node: '{node_name}'\n"
            for rc in remote_connection:
                remote_info_str += f"\t- {rc['type']}: '{rc['name']}' ({rc['hostname']}:{rc['port']}->{rc.get('localPort', '')}{rc.get('connection', '')})\n"
        perform_action = ask_for_confirmation(
            args, f"Are you sure you want to remove the following remote connections?\n{remote_info_str}"
        )

        for node_name, remote_connection in tunnels_to_remove.items():
            serial_number = next(node["serialNumber"] for node in nodes if node["name"] == node_name)
            node_handle = ms_nodes.Node(serial_number)
            if perform_action:
                node_handle.remove_remote_connection(remote_connection)
            else:
                log.info(
                    "Skipping removing remote connection %s from node %s",
                    remote_connection["name"],
                    node_name,
                )
    if args.establish:
        ret_value = 0

        connect_info_str = ""
        for node in nodes:
            for remote_element in node["remote_connections"]:
                connect_info_str += f"Node: '{node['name']}' - Remote Connection: '{remote_element['name']}' ({remote_element['type']})\n"
        perform_action = ask_for_confirmation(
            args,
            f"Are you sure you want to establish the following remote connections using a webbrowser call?\n{connect_info_str}",
        )

        for node in nodes:
            node_name = node["name"]
            remotes = node["remote_connections"]
            for remote_element in remotes:
                if not perform_action:
                    log.info(
                        "Skipping establishing remote connection %s for node %s",
                        remote_element["name"],
                        node_name,
                    )
                    continue
                log.info(
                    "Establishing remote connection for node %s: %s", node["name"], remote_element["name"]
                )
                node_handle = ms_nodes.Node(node["serialNumber"])
                url = node_handle.get_remote_connections(remote_element["name"])

                # if os is linux use call "xdg-open" with url instead
                if os.name == "posix":
                    if os.environ.get("WSL_DISTRO_NAME"):  # WSL
                        ret_value += subprocess.call(["wslview", url])
                    else:  # Linux
                        ret_value += subprocess.call(["xdg-open", url])
                else:
                    webbrowser.open(url, new=0, autoraise=True)
                    ret_value = 0
                if (
                    remote_element != remotes[-1]
                ):  # If not the last remote connection, wait before opening the next URL
                    time.sleep(3)  # Wait for 3 seconds before opening the next URL
        return ret_value
    if args.url:
        ret_value = 0
        remotes_file = []

        connect_info_str = ""
        for node in nodes:
            for remote_element in node["remote_connections"]:
                connect_info_str += f"Node: '{node['name']}' - Remote Connection: '{remote_element['name']}' ({remote_element['type']})\n"
        perform_action = ask_for_confirmation(
            args,
            f"Are you sure you want to create a connection url for the following remote connections?\n{connect_info_str}",
        )

        for node in nodes:
            node_name = node["name"]
            remotes = node["remote_connections"]
            remotes_file.append({"node_name": node_name, "urls": []})
            for remote_element in remotes:
                if not perform_action:
                    log.info(
                        "Skipping establishing remote connection %s for node %s",
                        remote_element["name"],
                        node_name,
                    )
                    continue
                log.info(
                    "Establishing remote connection for node %s: %s", node["name"], remote_element["name"]
                )
                node_handle = ms_nodes.Node(node["serialNumber"])
                url = node_handle.get_remote_connections(remote_element["name"])
                remotes_file[-1]["urls"].append(url)
        file_write(args.work_dir, args.output, remotes_file, output_methods=["stdout", "key", "file"])
        return ret_value

    if args.prune_remote_connections:
        active_connections = ms_nodes.get_active_remote_connections()
        for entry in active_connections:
            log.debug("Connection established by %s", entry["connectionRequest"]["requestedBy"])
        ms_user = MSUser(ms_nodes.ms)
        user_id = ms_user.get(ms_nodes.ms.usr)["_id"]
        remote_ids = []
        for entry in active_connections:
            if entry["connectionRequest"]["userId"] != user_id:
                continue
            remote_ids.append({
                "connectionUid": entry["connection"]["connectionUid"],
                "connectionRequestUid": entry["connectionRequest"]["requestUid"],
                "serialNumber": entry["connection"]["serialNumber"],
                "connectionName": entry["name"],
                "type": entry["connection"]["type"],
                "versionId": entry["connection"]["target"]["versionId"],
                "workloadId": entry["connection"]["target"]["workloadId"],
            })
        prune_info_str = ""
        if not remote_ids:
            log.info(
                "No active remote connections found for user '%s'", ms_user.get(ms_nodes.ms.usr)["username"]
            )
            return 0
        for entry in remote_ids:
            prune_info_str += f"Node with serial number '{entry['serialNumber']}' - Remote Connection: '{entry['connectionName']}' ({entry['type']})\n"
        perform_action = ask_for_confirmation(
            args,
            f"Are you sure you want to remove the following active remote connections for user '{ms_user.get(ms_nodes.ms.usr)['username']}'?\n{prune_info_str}",
        )
        if not perform_action:
            log.info(
                "Skipping pruning active remote connections for user '%s'",
                ms_user.get(ms_nodes.ms.usr)["username"],
            )
            return 0
        ms_nodes.remove_active_remote_connections(remote_ids)
    return 0
