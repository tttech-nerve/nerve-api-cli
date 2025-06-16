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

from .utils import args_interactive
from .utils import file_read
from .utils import file_write


def args_labels(parser):
    # mandatory args
    parser.add_argument(
        "-f",
        "--file",
        default="labels.json",
        help="Filename or blank for 'lables.json'. The '.json' ending is automatically appended if not provided.",
    )

    required_group = parser.add_argument_group("Mutually exclusive arguments for action")
    action_group = required_group.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "-l",
        "--list",
        help="Read labels form managmenet system",
        action="store_true",
    )

    action_group.add_argument(
        "-a",
        "--add",
        help="Add labels from the file to the managmenet system.",
        action="store_true",
    )

    action_group.add_argument(
        "-d",
        "--delete",
        help="Delete labels from file from the managmenet system.",
        action="store_true",
    )


def labels(ms_label, work_dir, arg, log=None):
    if not log:
        log = logging.getLogger(__name__)
    args = args_interactive(
        arg,
        args_labels,
        "Manage remote tunnels of a node. The node_tunnel file will be updated or created if it does not exist.",
    )

    # Process the arguments as needed
    if args.list:
        labels = ms_label.fetch_labels()
        labels = [{"key": label.get("key"), "value": label.get("value")} for label in labels.get("data", [])]
        file_write(work_dir, args.file, labels)
        log.info(
            "Labels read from management system and written to %s:\n%s",
            args.file,
            json.dumps(labels, indent=4),
        )
    if args.add:
        labels = file_read(work_dir, args.file)
        for label in labels:
            ms_label.create_label(label.get("key"), label.get("value"))
    if args.delete:
        labels = file_read(work_dir, args.file)
        for label in labels:
            ms_label.delete(label.get("key"), label.get("value"))
