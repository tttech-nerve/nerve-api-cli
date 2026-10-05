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
import re

import yaml
from nerve_lib import MSUser

from .utils import args_interactive
from .utils import ask_for_confirmation
from .utils import file_read
from .utils import file_write


def _access_token_action_parser(action_parser, action_name, help_text):
    parser = action_parser.add_parser(action_name, help=help_text)
    parser.set_defaults(ms_access_token_action=action_name)
    return parser


def _add_output_argument(parser, default, extra_formats=""):
    parser.add_argument(
        "--output",
        metavar="DESTINATION",
        default=default,
        help=f"Output destination: FILE path (e.g., '{default}'), stdout:json, stdout:yaml{extra_formats}",
    )


def args_ms_access_token(parser):
    action_parser = parser.add_subparsers(
        dest="ms_access_token_action", required=True, help="Available ms-access-token actions"
    )

    list_parser = _access_token_action_parser(
        action_parser, "list", "List access tokens from Management System and save to OUTPUT."
    )
    _add_output_argument(list_parser, "access_tokens.json")

    create_parser = _access_token_action_parser(
        action_parser, "create", "Create an access token on the Management System."
    )
    create_parser.add_argument("name", metavar="NAME", help="Name of the access token to create.")
    create_parser.add_argument(
        "--permissions",
        metavar="FILE",
        default="permissions.json",
        help="File containing permissions to assign to the access token. Permissions are read from a file",
    )
    create_parser.add_argument(
        "--expiration-date",
        metavar="DATE",
        help="Expiration date for the access token in YYYY-MM-DD format.",
    )
    _add_output_argument(create_parser, "access_token.json", extra_formats=", or stdout:token")

    delete_parser = _access_token_action_parser(
        action_parser, "delete", "Delete an access token from the Management System."
    )
    delete_parser.add_argument("name", metavar="NAME", help="Name of the access token to delete.")

    revoke_parser = _access_token_action_parser(
        action_parser, "revoke", "Revoke an access token from the Management System."
    )
    revoke_parser.add_argument("name", metavar="NAME", help="Name of the access token to revoke.")

    unlock_parser = _access_token_action_parser(
        action_parser,
        "unlock-brute-force",
        "Unlock the brute-force protection for an access token.",
    )
    unlock_parser.add_argument("name", metavar="NAME", help="Name of the access token to unlock.")

    permissions_parser = _access_token_action_parser(
        action_parser, "permissions", "List all available permissions and save to OUTPUT."
    )
    _add_output_argument(permissions_parser, "permissions.json")


def format_expiration_date(date_str):
    """Check if the date string is in YYYY-MM-DD format."""
    if not date_str:
        return ""

    pattern = r"^\d{4}-\d{2}-\d{2}$"
    if not re.match(pattern, date_str):
        raise ValueError(f"Date '{date_str}' is not in YYYY-MM-DD format.")

    return date_str + "T00:00:00.000Z"


def _get_ms_access_token_action(args):
    return getattr(args, "ms_access_token_action", "")


def ms_access_token(parent, arg, log=None):  # ruff: ignore[too-many-return-statements]
    log = log.getChild(__name__.split(".")[-1]) if log else logging.getLogger(__name__)

    args = args_interactive(arg, args_ms_access_token, "Manage access tokens for the Nerve Management system")
    if not args:
        return 2

    args.work_dir = parent.args.work_dir
    args.dry_run = parent.args.dry_run
    args.yes = parent.args.yes

    ms_user = MSUser(parent.ms)
    action = _get_ms_access_token_action(args)

    if action == "list":
        tokens = ms_user.get_access_tokens()
        log.info("Fetched %d access token(s).", len(tokens))
        log.info("%s", yaml.dump(tokens, indent=4, default_flow_style=False))
        file_write(args.work_dir, args.output, tokens, output_methods=["stdout", "file", "key"])
        return 0

    if action == "create":
        perform_action = ask_for_confirmation(
            args, f"Are you sure you want to create an access token '{args.name}'?"
        )
        if not perform_action:
            log.info("Access token creation skipped.")
            return 0

        permissions = file_read(args.work_dir, args.permissions, input_methods=["file", "stdin"])

        token = ms_user.create_access_token(
            name=args.name,
            permissions=permissions,
            expiration_date=format_expiration_date(args.expiration_date),
        )
        file_write(args.work_dir, args.output, token, output_methods=["stdout", "key", "file"])
        log.info("Access token '%s' created successfully.", args.name)
        return 0

    if action == "delete":
        perform_action = ask_for_confirmation(
            args, f"Are you sure you want to delete the access token '{args.name}'?"
        )
        if not perform_action:
            log.info("Access token deletion skipped.")
            return 0

        ms_user.delete_access_token(token_name=args.name)
        log.info("Access token '%s' deleted successfully.", args.name)
        return 0

    if action == "revoke":
        perform_action = ask_for_confirmation(
            args, f"Are you sure you want to revoke the access token '{args.name}'?"
        )
        if not perform_action:
            log.info("Access token revocation skipped.")
            return 0

        ms_user.revoke_access_token(token_name=args.name)
        log.info("Access token '%s' revoked successfully.", args.name)
        return 0

    if action == "unlock-brute-force":
        perform_action = ask_for_confirmation(
            args,
            f"Are you sure you want to unlock the brute-force protection for the access token '{args.name}'?",
        )
        if not perform_action:
            log.info("Unlocking brute-force protection skipped.")
            return 0

        token = ms_user.get_access_tokens(name=args.name)
        ms_user.unblock_access_token_brute_force(token_id=token["_id"])
        log.info("Brute-force protection for access token '%s' unlocked successfully.", args.name)
        return 0

    if action == "permissions":
        permissions = ms_user.get_access_token_creation_permissions()
        log.info("Fetched %d permission(s).", len(permissions))
        file_write(args.work_dir, args.output, permissions, output_methods=["stdout", "file"])
        return 0

    log.error("No valid action specified")
    return 2
