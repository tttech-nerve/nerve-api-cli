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
import os

from nerve_lib import MSLabel

from .utils import ask_for_confirmation
from .utils import file_read
from .utils import file_write


def args_ms_nodes_labels(parser):
    parser.title = "Manage labels on nodes from INPUT. If no label options are provided, the labels on nodes will be listed to INFO log."
    parser.add_argument(
        "--add",
        metavar="KEY=VALUE",
        action="append",
        help="Add or update labels on nodes from INPUT.",
    )
    parser.add_argument(
        "--delete",
        metavar="KEY",
        action="append",
        help="Delete labels on nodes from INPUT.",
    )
    parser.add_argument(
        "--edit",
        metavar="KEY=VALUE",
        action="append",
        help="Edit labels on nodes from INPUT.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="continue delete/edit operation also if label does not exist on node",
    )
    parser.add_argument(
        "--export",
        metavar="PATH",
        help="Export labels from nodes to a file-path.",
        type=str,
    )
    parser.add_argument(
        "--import",
        dest="import_labels",
        metavar="FILE",
        help="Import labels from FILE to nodes.",
        type=str,
    )


def ms_nodes_labels(ms_nodes, nodes, args, log):
    """Manage labels on nodes from INPUT using label options."""

    ms_label = MSLabel(ms_nodes.ms)
    # Implement the logic to manage labels on nodes

    action_str = (
        "add"
        if args.add
        else "edit"
        if args.edit
        else "delete"
        if args.delete
        else "export"
        if args.export
        else "import"
        if args.import_labels
        else "list"
    )
    if "list" == action_str:
        perform_action = True
    else:
        perform_action = ask_for_confirmation(
            args,
            f"Are you sure you want to {action_str} labels on '{', '.join(node['name'] for node in nodes)}'?",
        )

    for node in nodes:
        ms_node = ms_nodes.Node(node["serialNumber"])
        if action_str == "list":
            labels = ms_label.get_node_labels(ms_node)
            log.info("Labels on node '%s':", ms_node.serial_number)
            for label in labels:
                log.info(
                    "  %s=%s %s",
                    label["key"],
                    label["value"],
                    f"(created at {label['createdAt']})" if "createdAt" in label else "",
                )
        for label in args.add or []:
            key, value = label.split("=", 1)
            if perform_action:
                ms_label.add_node_label(ms_node, key, value)
            else:
                log.info("Skipping adding label '%s=%s' to node '%s'", key, value, ms_node.serial_number)
        for label in args.edit or []:
            key, value = label.split("=", 1)
            try:
                if perform_action:
                    ms_label.edit_node_label(ms_node, key, value)
                else:
                    log.info("Skipping editing label '%s=%s' on node '%s'", key, value, ms_node.serial_number)
            except ValueError:
                if not args.force:
                    raise
        for key in args.delete or []:
            try:
                if perform_action:
                    ms_label.del_node_label(ms_node, key)
                else:
                    log.info("Skipping deleting label '%s' from node '%s'", key, ms_node.serial_number)
            except ValueError:
                if not args.force:
                    raise

        if args.export:
            if perform_action:
                content = ms_label.export_node_labels(ms_node)
                file_write(
                    args.work_dir, os.path.join(args.export, f"labels_{ms_node.serial_number}.yaml"), content
                )
            else:
                log.info(
                    "Skipping exporting labels from node '%s' to '%s'", ms_node.serial_number, args.export
                )
        if args.import_labels:
            if perform_action:
                content = file_read(args.work_dir, args.import_labels)
                ms_label.import_node_labels(ms_node, content)
            else:
                log.info(
                    "Skipping importing labels to node '%s' from '%s'",
                    ms_node.serial_number,
                    args.import_labels,
                )
