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


"""Function for creating a new workload on the management system"""

import logging
import posixpath
from pathlib import Path

from .utils import args_interactive
from .utils import file_read
from .utils import file_write
from .utils import clean_wl_definition


def args_workload_create(parser):
    # mandatory args
    parser.add_argument(
        "-f",
        "--file",
        metavar="FILE_NAME",
        default="wl_def.json",
        help=(
            "Specify the file name for storing a template or containing the workload definition to be created on the MS"
            ". Defaults to 'wl_def.json' if omitted. '.json' is appended if not included."
        ),
    )

    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "-t",
        "--template",
        help="Create a workload template and write it to the 'file'.",
        choices=["docker", "registry", "codesys", "vm", "docker-compose"],
    )

    action_group.add_argument(
        "-c",
        "--create",
        help="Create a workload on the management system based on the 'file' template.",
        action="store_true",
    )

    parser.add_argument(
        "-p",
        "--path",
        default="",
        help="Path(s) to file(s) that are needed for creating the workload. Not required for docker-registry workloads. Multiple files can be specified by separating them with a comma. Wildcards are supported. (e.g. nerve-ds/*.tar,nerve-ds/*.yml)",
    )


def workload_create(ms_workloads, work_dir, arg, log=None):
    """Create a single workload on the management system"""
    def create_individual_workload(wl):
        if type(wl) is not dict:
            raise TypeError("Workload definition must be a dictionary")
        api_version = 3 if wl["type"] == "docker-compose" else 2
        search_pathes = [posixpath.join(work_dir, file_path) for file_path in args.path.split(",")]
        file_pathes = []
        for search_path in search_pathes:
            file_pathes += [file_path.as_posix() for file_path in Path.cwd().glob(search_path)]
        log.debug("Working with file pathes: \n    - %s", "\n    - ".join(file_pathes))
        wl = clean_wl_definition(wl)
        ms_workloads.provision_workload(wl, file_pathes, api_version)

    if not log:
        log = logging.getLogger(__name__)
    args = args_interactive(
        arg, args_workload_create, "Create a workload on the management system based on the given template."
    )
    if not args:
        return
    # Process the arguments as needed

    if args.template:
        networks = ["bridge"]
        remote_connections = [
            {
                "type": "TUNNEL",
                "name": "test_tunnel",
                "acknowledgment": "No",
                "hostname": "127.0.0.1",
                "port": 8080,
                "localPort": 8080,
            }
        ]
        if args.template == "docker":
            file_paths = ["nginx.tar.gz"]
        if args.template == "registry":
            file_paths = ["arvindr226/alpine-ssh"]
        if args.template == "vm":
            file_paths = ["slitaz_small.qcow2", "slitaz_small.qcow2.xml"]
            networks = [{"type": "Bridged", "interface": "isolated1"}]
            remote_connections = [
                {
                    "type": "TUNNEL",
                    "name": "Remote Desktop",
                    "acknowledgment": "No",
                    "hostname": "172.20.2.50",
                    "port": 3389,
                    "localPort": 3390,
                }
            ]
        if args.template == "codesys":
            file_paths = ["CodesysApp.zip"]
        if args.template == "docker-compose":
            file_paths = []
            remote_connections[0]["serviceName"] = "docker-compose-service"

        wl_template = ms_workloads.gen_workload_configuration(
            args.template,
            file_paths,
            wrkld_name="test_workload",
            wrkld_version_name="test_version",
            release_name="test_release",
            description="description text",
            label=[],
            networks=networks,
            ports=[{"protocol": "TCP", "host_port": 80, "container_port": 8080}],
            env_var=[{"env_variable": "test_var", "container_value": "var_value"}],
            remote_connections=remote_connections,
            restart_policy="always",
            limit_cpus=200,
            limit_memory={"unit": "MB", "value": 256},
            vm_snapshot={"enabled": True, "value": 1, "unit": "GB"},
            auth_usr="",
            auth_psw="",
        )

        file_write(work_dir, args.file, wl_template)

    elif args.create:
        wl_config = file_read(work_dir, args.file)
        if type(wl_config) is list:
            for i, wl in enumerate(wl_config):
                try:
                    create_individual_workload(wl)
                except TypeError as e:
                    log.warning("Workload creation failed for element %i: %s", i, e)
        else:
            try:
                create_individual_workload(wl_config)
            except TypeError as e:
                log.error("Unable to interpret file. Workload creation failed: %s", e)
