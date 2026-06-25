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

import logging

from .utils import args_interactive
from .utils import ask_for_confirmation
from .utils import file_read
from .utils import file_write


def args_ms_labels(parser):
    action_parser = parser.add_subparsers(
        dest="ms_labels_action", required=True, help="Available ms_labels actions"
    )

    list_parser = action_parser.add_parser(
        "list", help="Read labels from Management System and save to OUTPUT."
    )
    list_parser.set_defaults(ms_labels_action="list")
    list_parser.add_argument(
        "--output",
        metavar="DESTINATION",
        default="labels.json",
        help="Output destination: FILE path (e.g., 'output.json'), stdout:json, stdout:yaml, or stdout:pairs",
    )

    for action_name, help_text in {
        "add": "Add labels from INPUT to Management System.",
        "delete": "Delete labels from INPUT from Management System.",
    }.items():
        action_subparser = action_parser.add_parser(action_name, help=help_text)
        action_subparser.set_defaults(ms_labels_action=action_name)
        action_subparser.add_argument(
            "--input",
            metavar="SOURCE",
            default="labels.json",
            help="Input source for labels: FILE path (e.g., 'labels.json'), stdin:json, stdin:yaml, or pairs:key1:value1,key2:value2",
        )


def _get_ms_labels_action(args):
    return getattr(args, "ms_labels_action", "")


def ms_labels(parent, arg, log=None):
    log = log.getChild(__name__.split(".")[-1]) if log else logging.getLogger(__name__)
    args = args_interactive(
        arg,
        args_ms_labels,
        "Manage labels of a node. The labels file will be updated or created if it does not exist.",
    )
    if not args:
        return 2

    ms_label = parent.ms_labels
    args.work_dir = parent.args.work_dir
    args.yes = parent.args.yes
    args.dry_run = parent.args.dry_run
    action = _get_ms_labels_action(args)

    # Process the arguments as needed
    if action == "list":
        labels = ms_label.fetch_labels()
        labels = [{"key": label.get("key"), "value": label.get("value")} for label in labels.get("data", [])]
        file_write(args.work_dir, args.output, labels, output_methods=["stdout", "pairs", "file"])
        return 0

    labels = file_read(args.work_dir, args.input, input_methods=["stdin", "pairs", "file"])

    if isinstance(labels, dict):
        labels = [labels]

    if action == "add":
        perform_action = ask_for_confirmation(
            args, f"Are you sure you want to add {len(labels)} labels to {args.ms_url}?"
        )

        for label in labels:
            if perform_action:
                ms_label.create_label(label.get("key"), label.get("value"))
            else:
                log.info("Skipping adding label %s", f"{label.get('key')}:{label.get('value')}")
        return 0
    if action == "delete":
        perform_action = ask_for_confirmation(
            args, f"Are you sure you want to delete {len(labels)} labels from {args.ms_url}?"
        )
        for label in labels:
            if perform_action:
                ms_label.delete(label.get("key"), label.get("value"))
            else:
                log.info("Skipping deleting label %s", f"{label.get('key')}:{label.get('value')}")
        return 0

    log.error("No valid action specified")
    return 2
