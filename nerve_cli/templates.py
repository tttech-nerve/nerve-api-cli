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


"""Function for creating a new workload on the management system"""

import logging

from .utils import args_interactive
from .utils import file_write


def args_templates(parser):
    action_parser = parser.add_subparsers(
        dest="template_action", required=True, help="Available template actions"
    )

    workload_parser = action_parser.add_parser(
        "workload",
        help="Generate workload templates.",
    )
    workload_parser.set_defaults(template_action="workload")
    workload_parser.add_argument(
        "workload",
        metavar="TYPE",
        choices=["docker", "registry", "vm", "codesys", "docker-compose"],
        help="Generate workload template of selected type: docker, registry, vm, codesys, or docker-compose",
    )
    workload_parser.add_argument(
        "--output",
        metavar="DESTINATION",
        default="template.json",
        help="Output destination: FILE path (e.g., 'template.json'), stdout:json, or stdout:yaml",
    )
    workload_parser.add_argument(
        "--all-options", help="Include all optional fields in generated template", action="store_true"
    )
    workload_parser.add_argument(
        "--internal-docker-registry",
        action="store_true",
        help="Use internal Docker registry in templates",
    )
    workload_parser.add_argument(
        "--external-docker-registry",
        action="store_true",
        help="Use external Docker registry in templates",
    )

    remote_connections_parser = action_parser.add_parser(
        "remote-connections",
        help="Generate remote connection templates.",
    )
    remote_connections_parser.set_defaults(template_action="remote-connections")
    remote_connections_parser.add_argument(
        "remote_connections",
        metavar="TYPE",
        choices=["tunnel", "screen"],
        help="Generate template with remote connections of selected type: tunnel or screen",
    )
    remote_connections_parser.add_argument(
        "--output",
        metavar="DESTINATION",
        default="template.json",
        help="Output destination: FILE path (e.g., 'template.json'), stdout:json, or stdout:yaml",
    )
    remote_connections_parser.add_argument(
        "--all-options", help="Include all optional fields in generated template", action="store_true"
    )


def _get_template_action(args):
    return getattr(args, "template_action", "")


def nerve_templates(parent, arg, log=None):
    """Create a single workload on the management system"""
    log = log.getChild(__name__.split(".")[-1]) if log else logging.getLogger(__name__)
    args = args_interactive(
        arg, args_templates, "Create a workload on the management system based on the given template."
    )
    if not args:
        return 2

    ms_workloads = parent.ms_workloads
    args.work_dir = parent.args.work_dir

    if _get_template_action(args) == "workload":
        networks = ["bridge", "isolated1"]
        compose_dict = {}
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
        if args.workload == "docker":
            file_paths = ["nginx.tar.gz"]
        if args.workload == "registry":
            file_paths = ["arvindr226/alpine-ssh"]
        if args.workload == "vm":
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
        if args.workload == "codesys":
            file_paths = ["CodesysApp.zip"]
        if args.workload == "docker-compose":
            file_paths = [
                "docker-compose.yaml",
                "ds-gateway-2.0.41.tar",
                "ds-grafana-1.1.14.tar",
                "ds-timescaledb-1.1.16.tar",
                "ds-supervisor-be-1.1.29.tar",
            ]
            remote_connections[0]["serviceName"] = "docker-compose-service"
            compose_dict = {
                "services": {
                    "gateway": {
                        "volumes": ["config_and_certs:/app/user_config", "credentials:/app/credentials"]
                    }
                }
            }

        provision_type = args.workload
        provision_type = (
            "registry" if args.workload == "docker" and args.external_docker_registry else provision_type
        )
        api_version = (
            3
            if provision_type == "docker-compose"
            or (provision_type == "docker" and args.internal_docker_registry)
            else 2
        )
        if args.all_options:
            wl_template = ms_workloads.gen_workload_configuration(
                provision_type,
                file_paths,
                wrkld_name="test_workload",
                wrkld_version_name="test_version",
                container_name="test_container",
                release_name="test_release",
                description="description text",
                # label=["label1", "label2"],  # currently not supported
                networks=networks,
                ports=[{"protocol": "TCP", "host_port": 80, "container_port": 8080}],
                docker_volumes=[
                    {
                        "volumeName": "workload_data",
                        "containerPath": "/container/data",
                        "configurationStorage": True,
                    }
                ],
                restart_on_config_update=True,
                env_var=[{"env_variable": "test_var", "container_value": "var_value"}],
                remote_connections=remote_connections,
                restart_policy="always",
                limit_cpus=200,
                limit_memory={"unit": "MB", "value": 256},
                released=False,
                vm_num_cpus=2,
                vm_memory={"unit": "MB", "value": 1024},
                vm_snapshot={"enabled": True, "value": 1, "unit": "GB"},
                compose_dict=compose_dict,
                docker_config_volumes=[
                    {
                        "service": "gateway",
                        "volume_id": 0,
                        "restart_on_update": False,
                    }
                ],
                auth_usr="username",
                auth_psw="pa$sw0rd",  # pragma: allowlist secret
                api_version=api_version,
                internal_docker_registry=args.internal_docker_registry,
            )
        else:
            wl_template = ms_workloads.gen_workload_configuration(
                provision_type,
                wrkld_name="test_workload",
                wrkld_version_name="test_version",
                api_version=api_version,
                internal_docker_registry=args.internal_docker_registry,
            )

        if (
            provision_type == "docker-compose"
            or (provision_type == "docker" and args.internal_docker_registry)
        ) and args.all_options:
            wl_template["versions"][0]["files"] = [{"originalName": name} for name in file_paths]

        file_write(args.work_dir, args.output, wl_template, output_methods=["stdout", "file"])

    if _get_template_action(args) == "remote-connections":
        if args.remote_connections == "tunnel":
            file_write(
                args.work_dir,
                args.output,
                [
                    {
                        "hostname": "172.20.2.1",
                        "localPort": 3333,
                        "port": 3333,
                        "acknowledgment": "No",
                        "type": "TUNNEL",
                        "name": "LocalUi",
                    },
                    {
                        "hostname": "172.20.3.2",
                        "localPort": 11740,
                        "port": 11740,
                        "acknowledgment": "No",
                        "type": "TUNNEL",
                        "name": "Codesys IDE",
                    },
                ],
                output_methods=["stdout", "file"],
            )
        elif args.remote_connections == "screen":
            file_write(
                args.work_dir,
                args.output,
                [
                    {  # pragma: allowlist secret
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
                output_methods=["stdout", "file"],
            )

    return 0
