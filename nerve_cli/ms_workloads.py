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


"""Function for listing workloads"""

import logging

from .ms_workloads_export import ms_workloads_export
from .ms_workloads_provision import ms_workloads_provision
from .utils import args_interactive
from .utils import ask_for_confirmation
from .utils import file_read
from .utils import file_write
from .utils_nodes import normalize_nodes_input
from .utils_workloads import check_filter_arg
from .utils_workloads import human_readable_output
from .utils_workloads import normalize_workloads_input
from .utils_workloads import validate_ms_workload_read_error


def args_ms_workloads_list(parser):
    filter_args = parser.add_argument_group("Filter arguments for getting workloads list")
    filter_args.add_argument(
        "--type",
        metavar="TYPE",
        default="",
        help="Filter by workload type: docker, codesys, vm, or docker-compose",
        choices=["docker", "codesys", "vm", "docker-compose"],
    )
    filter_args.add_argument(
        "--name",
        metavar="PATTERN",
        default="",
        help="Filter by workload name. Supports regex with prefix 'regex:' (e.g., 'regex:app.*', 'myapp')",
    )
    filter_args.add_argument("--disabled", help="Include disabled workloads in results", action="store_true")


def args_ms_workloads_list_versions(parser):
    filter_version_args = parser.add_argument_group(
        "Filter arguments to only include specific workload versions in the list results"
    )
    filter_version_args.add_argument(
        "--version-name",
        metavar="PATTERN",
        help="Filter by version name. Supports regex with prefix 'regex:' (e.g., 'regex:v[0-9]+', 'v1.0')",
    )
    filter_version_args.add_argument(
        "-r",
        "--version-release-name",
        metavar="PATTERN",
        help="Filter by release name. Supports regex with prefix 'regex:' (e.g., 'regex:release_.*', 'stable')",
    )
    filter_version_args.add_argument(
        "--version-size",
        default="",
        help=(
            "Filter versions by size: use '<500MB' or '>2GB' (Linux/macOS shells), or "
            "'lt:500MB'/'gt:2GB' (Windows-friendly). Units: B, KB, MB, GB, TB"
        ),
    )
    filter_version_args.add_argument(
        "--version-date",
        metavar="FILTER",
        help=(
            "Filter versions by date: use '<2024-01-15' or '>2024-01-01' (Linux/macOS shells), "
            "or 'lt:2024-01-15'/'gt:2024-01-01' (Windows-friendly); format: YYYY-MM-DD"
        ),
    )
    filter_version_args.add_argument(
        "--version-list-filter",
        metavar="RANGE",
        help="Filter versions by range (Python slicing): '0:5' (first 5), '-5:' (last 5), '3' (4th version)",
    )


def args_ms_workloads(parser):
    action_parser = parser.add_subparsers(
        dest="ms_workloads_action", required=True, help="Available ms_workloads actions"
    )

    list_parser = action_parser.add_parser(
        "list",
        help="List workloads and versions from Management System and save to OUTPUT.",
    )
    list_parser.set_defaults(ms_workloads_action="list")
    list_parser.add_argument(
        "--output",
        metavar="DESTINATION",
        default="workloads.json",
        help=(
            "Output destination: FILE path (e.g., 'output.json', '/path/to/file.json'), "
            "stdout:json, stdout:yaml, or stdout:key (e.g., stdout:name, stdout:_id)"
        ),
    )
    list_parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validation of workload details when listing workloads (faster, but may miss errors)",
    )
    args_ms_workloads_list(list_parser)
    args_ms_workloads_list_versions(list_parser)

    export_parser = action_parser.add_parser(
        "export",
        help="Download workloads and versions from INPUT to PATH/WORKLOAD_NAME/VERSION_NAME/.",
    )
    export_parser.set_defaults(ms_workloads_action="export")
    export_parser.add_argument(
        "export",
        metavar="PATH",
        help=(
            "Download workloads/versions from INPUT to PATH/WORKLOAD_NAME/VERSION_NAME/ "
            "(absolute PATH supported; includes definition and files)"
        ),
    )
    export_parser.add_argument(
        "--input",
        metavar="SOURCE",
        default="workloads.json",
        help=(
            "Input source for workloads: FILE path (e.g., 'workloads.json', '/path/to/file.json'), "
            "stdin:json, stdin:yaml, name:workload1,workload2, or _id:id1,id2"
        ),
    )
    export_parser.add_argument(
        "--template",
        action="store_true",
        help=(
            "Export only the workload definition (and docker-compose file if applicable) without"
            " including the workload files (e.g., docker images, CODESYS packages)"
        ),
    )
    args_ms_workloads_list_versions(export_parser)

    provision_parser = action_parser.add_parser(
        "provision",
        help="Upload workloads from INPUT to Management System using PATH for workload files.",
    )
    provision_parser.set_defaults(ms_workloads_action="provision")
    provision_parser.add_argument(
        "provision",
        metavar="PATH",
        help=(
            "Upload workloads from INPUT to Management System using PATH for workload files "
            "(absolute PATH supported; supports comma-separated paths)"
        ),
    )
    provision_parser.add_argument(
        "--input",
        metavar="SOURCE",
        default="workloads.json",
        help=(
            "Input source for workloads: FILE path (e.g., 'workloads.json', '/path/to/file.json'), "
            "stdin:json, stdin:yaml, name:workload1,workload2, or _id:id1,id2"
        ),
    )
    provision_parser.add_argument(
        "--registry",
        help="Provision docker/docker-compose as registry workloads (docker registry source)",
        action="store_true",
    )
    provision_parser.add_argument(
        "--legacy",
        help="Provision docker/docker-compose as legacy workloads (older format)",
        action="store_true",
    )

    delete_parser = action_parser.add_parser(
        "delete",
        help="Delete workloads and versions specified in INPUT from Management System.",
    )
    delete_parser.set_defaults(ms_workloads_action="delete")
    delete_parser.add_argument(
        "--input",
        metavar="SOURCE",
        default="workloads.json",
        help=(
            "Input source for workloads: FILE path (e.g., 'workloads.json', '/path/to/file.json'), "
            "stdin:json, stdin:yaml, name:workload1,workload2, or _id:id1,id2"
        ),
    )
    args_ms_workloads_list_versions(delete_parser)

    deploy_parser = action_parser.add_parser(
        "deploy",
        help="Deploy workloads from INPUT to NODES.",
    )
    deploy_parser.set_defaults(ms_workloads_action="deploy")
    deploy_parser.add_argument(
        "deploy",
        metavar="NODES",
        help=(
            "Deploy workloads from INPUT to NODES. NODES: FILE path, stdin:json, stdin:yaml, "
            "name:node1,node2, or serialNumber:serial1"
        ),
    )
    deploy_parser.add_argument(
        "--input",
        metavar="SOURCE",
        default="workloads.json",
        help=(
            "Input source for workloads: FILE path (e.g., 'workloads.json', '/path/to/file.json'), "
            "stdin:json, stdin:yaml, name:workload1,workload2, or _id:id1,id2"
        ),
    )
    deploy_parser.add_argument("--wait", help="Wait until deployment completes", action="store_true")
    args_ms_workloads_list_versions(deploy_parser)


def _get_ms_workloads_action(args):
    return getattr(args, "ms_workloads_action", "")


def ms_workloads_list(ms_workloads, args, log):
    """List workloads and their details from the management system based on the provided filters and store results to 'output'"""
    # ms_workloads_list main function
    output = []

    # get full list of all workloads
    filter_name = args.name if not args.name.startswith(("regex:", "regexp:")) else ""
    wl_list = ms_workloads.get_workloads_dict(
        read_versions=True, compact_dict=False, filter_name=filter_name, filter_type=args.type
    )
    log.info(
        "%d workloads including %d versions fetched from the '%s'",
        len(wl_list),
        sum(len(wl.get("versions", [])) for wl in wl_list),
        args.ms_url,
    )

    # apply workload level filters
    workloads_filtered = []
    for filer_name, arg_value in {
        "--name": args.name or "",
    }.items():
        if arg_value.startswith(("regex:", "regexp:")):
            log.info(
                "Filtering workloads by '%s' with regex pattern: '%s'", filer_name, arg_value.split(":", 1)[1]
            )
    for workload in wl_list:
        wl_name = workload["name"]
        if not check_filter_arg(args.name, wl_name):
            continue

        if not args.disabled and check_filter_arg(True, workload["disabled"]):
            continue

        workloads_filtered.append(workload)

    log.info(
        "%d workloads including %d versions matched workload filters",
        len(workloads_filtered),
        sum(len(wl.get("versions", [])) for wl in workloads_filtered),
    )

    output = normalize_workloads_input(workloads_filtered, args, ms_workloads, log)
    log.info(
        "%d workloads including %d versions matched workload version filters",
        len(output),
        sum(len(wl.get("versions", [])) for wl in output),
    )
    human_readable_output(output, log)

    # Check if all workload details can be read successfully
    failed_count = 0
    if not args.skip_validation:
        failed_count = validate_ms_workload_read_error(output, ms_workloads, log)

    file_write(args.work_dir, args.output, output, output_methods=["stdout", "key", "file"])
    if not output:
        log.warning("No workloads found with the provided filters")
        return 1
    return failed_count


def ms_workloads_delete(ms_workloads, workloads, args, log=None):
    num_versions = sum(len(workload.get("versions", [])) for workload in workloads)
    if len(workloads) == 0:
        log.error("No workloads found to delete with the provided filters")
        return 1
    perform_action = ask_for_confirmation(
        args,
        f"Are you sure you want to delete {len(workloads)} workload(s) with a total of {num_versions} version(s) from the management system?",
    )

    for workload in workloads:
        for version in workload["versions"]:
            if not perform_action:
                log.info(
                    "Skipping deletion of workload '%s' version '%s'",
                    workload["name"],
                    version["name"],
                )
                continue
            try:
                wl_version = ms_workloads.WorkloadVersion(
                    workload["name"], version["name"], version.get("releaseName")
                )
                wl_version.delete_workload_version()
            except ValueError as ex_msg:
                if "Workload with name" in str(ex_msg) and "not found" in str(ex_msg):
                    log.warning(
                        "Workload '%s' version '%s' not found on the management system, skipping deletion",
                        workload["name"],
                        version["name"],
                    )
                    continue
                raise ValueError(f"Workload version cannot be removed: {ex_msg}")
        wl_version = ms_workloads.WorkloadVersion(workload["name"])
        try:
            if not wl_version._get_versions():
                if not perform_action:
                    log.info(
                        "Skipping deletion of workload '%s' as it has no more versions after deletion",
                        workload["name"],
                    )
                    continue
                # all sub-version had been removed, deleting also the workload
                wl_version.delete_workload()
        except ValueError as ex_msg:
            if "Workload with name" in str(ex_msg) and "not found" in str(ex_msg):
                log.warning(
                    "Workload '%s' not found on the management system, skipping deletion",
                    workload["name"],
                )
                continue
            raise ValueError(f"Workload cannot be removed: {ex_msg}")
    return 0


def ms_workloads_deploy(ms_workloads, workloads, ms_nodes, args, log=None):
    nodes = normalize_nodes_input(
        file_read(args.work_dir, args.deploy, input_methods=["stdin", "name", "serialNumber", "_id", "file"]),
        ms_nodes,
    )
    node_list = []

    num_nodes = len(nodes)
    num_workloads = len(workloads)
    if num_workloads == 0 or num_nodes == 0:
        log.error(
            "No workloads or nodes defined to deploy. # Workloads found: %d, # Nodes found: %d with the provided filters",
            num_workloads,
            num_nodes,
        )
        return 1
    perform_action = ask_for_confirmation(
        args,
        f"Are you sure you want to deploy {num_workloads} workload(s) to {num_nodes} node(s)?",
    )

    if perform_action:
        for node in nodes:
            node_handle = ms_nodes.Node(node["serialNumber"])
            node_list.append(node_handle)

    for workload in workloads:
        if len(workload.get("versions", [])) > 1:
            log.warning(
                "Workload '%s' has no specific version defined, last version will be selected",
                workload["name"],
            )
            version = workload["versions"][-1]
            wl_version = ms_workloads.WorkloadVersion(
                workload["name"], version["name"], version.get("releaseName")
            )
        elif len(workload.get("versions", [])) == 0:
            log.warning(
                "Workload '%s' has no specific version defined, latest version will be selected",
                workload["name"],
            )
            wl_version = ms_workloads.WorkloadVersion(workload["name"])
        else:
            version = workload["versions"][-1]
            wl_version = ms_workloads.WorkloadVersion(
                workload["name"], version["name"], version.get("releaseName")
            )

        if not perform_action:
            log.info(
                "Skipping deployment of workload '%s' version '%s' to nodes '%s'",
                workload["name"],
                version["name"],
                ",".join(node["name"] for node in nodes),
            )
            continue
        if args.wait:
            wl_version.deploy_full(node_list)
        else:
            wl_version.deploy(node_list)
    return 0


def ms_workloads(parent, arg, log=None):
    log = log.getChild(__name__.split(".")[-1]) if log else logging.getLogger(__name__)
    args = args_interactive(
        arg,
        args_ms_workloads,
        "Operate on workloads of the management system.",
    )
    if not args:
        return 2

    ms_workloads = parent.ms_workloads
    ms_nodes = parent.ms_nodes
    args.work_dir = parent.args.work_dir
    args.yes = parent.args.yes
    args.dry_run = parent.args.dry_run
    action = _get_ms_workloads_action(args)

    if action == "list":
        return ms_workloads_list(ms_workloads, args, log)

    if action == "provision":
        return ms_workloads_provision(
            ms_workloads,
            file_read(args.work_dir, args.input, input_methods=["stdin", "name", "file"]),
            args,
            log,
        )

    workloads = normalize_workloads_input(
        file_read(args.work_dir, args.input, input_methods=["stdin", "name", "_id", "file"]),
        args,
        ms_workloads,
        log,
    )
    if action == "export":
        return ms_workloads_export(ms_workloads, workloads, args, log)
    if action == "delete":
        return ms_workloads_delete(ms_workloads, workloads, args, log)
    if action == "deploy":
        if args.input.startswith("stdin:") and args.deploy.startswith("stdin:"):
            raise ValueError(
                "Cannot read both workloads and nodes from stdin for deployment."
                " Please provide at least one of them via file input or direct definitions to avoid ambiguity."
            )
        return ms_workloads_deploy(ms_workloads, workloads, ms_nodes, args, log)

    log.error("No valid action specified")
    return 2
