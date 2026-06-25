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
from nerve_lib import LocalDockerVolumes
from nerve_lib import LocalNode
from nerve_lib import NodeHandle

from .utils import args_interactive
from .utils_docker_volumes import args_docker_volumes
from .utils_docker_volumes import docker_volumes


def args_local_node(parser):
    parser.add_argument(
        "--localui-password",
        default="",
        help="Password for logging into the local UI using default admin account",
    )
    parser.add_argument(
        "--ms-credentials",
        action="store_true",
        help=(
            "Use MS credentials for local UI login. Used when default local UI credentials "
            "are deactivated and MS login is allowed"
        ),
    )
    parser.add_argument(
        "--ip-address",
        metavar="NODE_IP_ADDRESS",
        default="172.20.2.1:3333",
        help="IP address and port of the local UI to connect to (e.g., 172.20.2.1:3333)",
    )

    action_parser = parser.add_subparsers(
        dest="local_node_action", required=True, help="Available local-node actions"
    )
    docker_volumes_parser = action_parser.add_parser(
        "docker-volumes",
        help="Manage Docker volumes through the local UI.",
    )
    docker_volumes_parser.set_defaults(local_node_action="docker-volumes")
    args_docker_volumes(docker_volumes_parser)


def _get_local_node_action(args):
    return getattr(args, "local_node_action", "")


def _connect_to_node(args, log):
    user = args.ms_user if args.ms_credentials else "local@nerve.cloud"
    password = args.ms_password if args.ms_credentials else args.localui_password

    log.info(
        "Connecting to node at '%s' for managing workloads and docker volumes through local UI",
        args.ip_address,
    )
    ip_addr, port = args.ip_address.split(":")
    node_handle = NodeHandle(ip_addr, local_bind_port=int(port))
    try:
        node_handle.login(user=user, password=password)
    except CheckStatusCodeError as ex_msg:
        if (
            ex_msg.status_code == requests.codes.bad_request
            and "default_admin_account_is_deactivated_use_your_personal_credentials_to_log_in"
            in ex_msg.response_text
            and args.ms_user
            and args.ms_password
        ):
            log.info(
                "Using MS-credentials of user '%s' to log in to local UI since default localui credentials are deactivated",
                args.ms_user,
            )
            node_handle.login(user=args.ms_user, password=args.ms_password)
        else:
            raise
    return node_handle


def get_node_serial(node_handle):
    local_node = LocalNode(node_handle)
    cloud_config = local_node.get_configuration()
    return cloud_config.get("serialNumber", "unknown_serial")


def local_node(parent, arg, log=None):
    log = log.getChild(__name__.split(".")[-1]) if log else logging.getLogger(__name__)

    args = args_interactive(arg, args_local_node, "List nodes and create a node list or add to the list")
    if not args:
        return 2

    args.work_dir = parent.args.work_dir
    args.dry_run = parent.args.dry_run
    args.yes = parent.args.yes

    if _get_local_node_action(args) == "docker-volumes":
        node_handle = _connect_to_node(args, log)
        local_volumes = LocalDockerVolumes(node_handle)
        serial_number = get_node_serial(node_handle)
        return docker_volumes([serial_number], args, local_volumes, log)

    return 1
