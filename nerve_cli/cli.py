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

"""Command line interface for nerve_lib API."""

import argparse
import cmd
import configparser
import logging
import os
import shlex
import subprocess
import sys
from functools import wraps

import requests
from nerve_lib import CheckStatusCodeError
from nerve_lib import MSHandle
from nerve_lib import MSLabel
from nerve_lib import MSNode
from nerve_lib import MSWorkloads
from nerve_lib import WorkloadDeployError
from nerve_lib import setup_logging

from .local_node import args_local_node
from .local_node import local_node
from .ms_labels import args_ms_labels
from .ms_labels import ms_labels
from .ms_nodes import args_ms_nodes
from .ms_nodes import ms_nodes
from .ms_workloads import args_ms_workloads
from .ms_workloads import ms_workloads
from .templates import args_templates
from .templates import nerve_templates
from .utils import args_interactive

setup_logging(compact=True)  # format_string="{levelname:<7} :: {message}")
logging.getLogger("docker").setLevel(logging.WARNING)
cli_log = logging.getLogger("CLI")


SHELL_ALLOWED_COMMANDS = {"cat", "cd", "echo", "ll", "ls", "nano", "notepad", "pwd", "vi", "vim"}
SHELL_COMMAND_ALIASES = {
    "ll": "ls",
}
SHELL_WINDOWS_COMMAND_ALIASES = {
    "dir": "ls",
    "type": "cat",
}


def _format_cli_error(ex_msg):
    emsg = "An error occured: "
    print_trace = False
    if isinstance(ex_msg, requests.exceptions.ConnectionError):
        if "Name or service not known" in str(ex_msg):
            emsg = "The URL of the Management System could not be resolved"
        else:
            emsg = f"Failed to connect to Management System: {ex_msg}"
    elif isinstance(ex_msg, (ValueError, AttributeError)):
        emsg = str(ex_msg)
        for err_text in [
            "No username/password provided for MS login",
            "No MS URL provided.",
            "Invalid format for log_level: ",
            "Invalid format for --filter-size",
            "Workload version cannot be removed",
            "already exists on the management system",
            "Node with name '",
            "Node with serial number '",
            "Cannot read both workloads and nodes from stdin",
            "More files were found for workload ",
            "The --backup option is only applicable when using MS connection",
            "Import of volume ",
            "Node item must contain either 'serialNumber' or 'name' key with valid value",
            "Workload with name '",
            "No shell command provided.",
            "Shell command '",
            "Command 'cat' requires at least one path argument.",
        ]:
            if err_text in str(ex_msg):
                break
        else:
            print_trace = True
    elif isinstance(ex_msg, (RuntimeError, FileNotFoundError, WorkloadDeployError)):
        emsg = str(ex_msg)
    elif "Invalid credentials" in str(ex_msg):
        emsg = "Failed to authorize (invalid credentials). Please check your credentials"
    elif isinstance(ex_msg, CheckStatusCodeError):
        emsg = f"API call failed: {ex_msg}"
    else:
        emsg += str(ex_msg)
        print_trace = True

    return emsg, print_trace


def handle_do_errors(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            self.last_exit_code = func(self, *args, **kwargs)
        except Exception as ex_msg:  # noqa: BLE001
            emsg, print_trace = _format_cli_error(ex_msg)
            self._log.error(emsg)
            if print_trace or self.args.log_level == "TRACE":
                self._log.exception(ex_msg)
            self.last_exit_code = 2
        return False  # to prevent cmd from exiting on exceptions

    return wrapper


def _register_dashed_command_aliases(cls):
    hidden_command_names = set()

    for attr_name, attr_value in list(vars(cls).items()):
        for prefix in ("do_", "help_", "complete_"):
            if not attr_name.startswith(prefix):
                continue

            command_name = attr_name[len(prefix) :]
            if "_" not in command_name:
                continue

            dashed_attr_name = f"{prefix}{command_name.replace('_', '-')}"
            if hasattr(cls, dashed_attr_name):
                continue

            setattr(cls, dashed_attr_name, attr_value)
            hidden_command_names.add(attr_name)
            break

    cls._hidden_command_names = frozenset(hidden_command_names)
    return cls


def _resolve_shell_command(command):
    normalized_command = command.lower()
    normalized_command = SHELL_COMMAND_ALIASES.get(normalized_command, normalized_command)
    if os.name == "nt":
        normalized_command = SHELL_WINDOWS_COMMAND_ALIASES.get(normalized_command, normalized_command)

    if normalized_command not in SHELL_ALLOWED_COMMANDS:
        allowed_commands = sorted(SHELL_ALLOWED_COMMANDS)
        if os.name == "nt":
            allowed_commands.extend(sorted(SHELL_WINDOWS_COMMAND_ALIASES))
        allowed_commands_text = ", ".join(allowed_commands)
        raise ValueError(
            f"Shell command '{command}' is not allowed. Allowed commands: {allowed_commands_text}."
        )

    return normalized_command


def _log_level_from_verbosity(verbosity, is_interactive_mode: bool) -> str:
    if not isinstance(verbosity, int):
        verbosity = 0
    verbosity = max(verbosity, 0)

    if is_interactive_mode:
        levels = ["INFO", "DEBUG", "TRACE"]
    else:
        levels = ["WARNING", "INFO", "DEBUG", "TRACE"]

    return levels[min(verbosity, len(levels) - 1)]


@_register_dashed_command_aliases
class NerveCLI(cmd.Cmd):
    intro = "Welcome to the nerve_lib CLI. Type help or ? to list commands.\n"
    prompt = "(nerve) "
    identchars = cmd.Cmd.identchars + "-"
    _hidden_command_names = frozenset()

    def __init__(self, args):
        super().__init__()
        self.last_exit_code = 0
        self.args = args

        self._log = logging.getLogger("CLI")
        self.do_log_level(args.log_level)

        os.makedirs(args.work_dir, exist_ok=True)

        ms_url, ms_user, ms_password = self._get_ms_user_password(args.ms_url, args.ms_user, args.ms_password)
        self.args.ms_user = ms_user
        self.args.ms_password = ms_password

        self.set_ms_url(ms_url, self.args.ms_user, self.args.ms_password)

        if ms_url:
            self._log.info("NerveCLI started for '%s'", ms_url)

    def _get_ms_user_password(self, ms_url, ms_user, ms_password):
        config = configparser.ConfigParser()
        config.read("credentials.ini")
        if not ms_url:
            ms_url_from_credentials = ""
            if len(config.sections()) == 1:
                ms_url_from_credentials = config.sections()[0]
            use_ms_url = os.getenv("MS_URL") or ms_url_from_credentials
            if not use_ms_url:
                return "", "", ""
        elif ms_url.startswith("http"):
            use_ms_url = ms_url.split("://")[1]
        else:
            use_ms_url = ms_url

        if not ms_user or not ms_password:
            # check if the section 'ms_url' exists
            if use_ms_url in config.sections():
                self._log.debug("Using credentials from credentials.ini for %s", use_ms_url)
                if not ms_user:
                    ms_user = config[use_ms_url]["username"]
                if not ms_password:
                    ms_password = config[use_ms_url]["password"]
            elif (not os.getenv("MS_USR") and not ms_user) or (not os.getenv("MS_PSW") and not ms_password):
                self._log.warning(
                    "No credentials provided for MS. Please provide credentials in the environment"
                    " variables MS_USR and MS_PSW or in the credentials.ini file."
                )
            else:
                self._log.debug("Using credentials from environment variables for %s", use_ms_url)
                ms_user = os.getenv("MS_USR")
                ms_password = os.getenv("MS_PSW")

        return use_ms_url, ms_user, ms_password

    def get_names(self):
        return [name for name in super().get_names() if name not in self._hidden_command_names]

    def set_ms_url(self, ms_url, ms_user, ms_password):
        if ms_url:
            self.ms = MSHandle(ms_url, ms_user, ms_password)
        else:
            # usage of MS handle will lead to an error if no MS URL is provided
            # Error is only raised when MS actually needs be be used, function not requiring this call (e.g. to create templates)
            # will work without MS URL
            class FakeCallMS:
                def __init__(self, ms_user="", ms_password="", *args, **kwargs):  # pragma: allowlist secret
                    self._log = logging.getLogger("CLI")
                    self.usr = ms_user
                    self.psw = ms_password
                    self.ms_url = ""

                @classmethod
                def _raise_no_ms_url(cls, *args, **kwargs):
                    raise ValueError(
                        "No MS URL provided. Please provide the MS URL in the environment"
                        " variable MS_URL or as an argument."
                        " If a credentials.ini file exists with only one section, the MS will be set to this."
                    )

                # any function call not defined shall lead to an error
                def __getattr__(self, name):
                    if name.lower() in {"get", "post", "put", "delete", "patch"}:
                        return self._raise_no_ms_url
                    raise ValueError(
                        "No MS URL provided. Please provide the MS URL in the environment"
                        " variable MS_URL or as an argument."
                        " If a credentials.ini file exists with only one section, the MS will be set to this."
                    )

            self.ms = FakeCallMS(ms_user, ms_password)

        self.ms_workloads = MSWorkloads(self.ms)

        self.ms_nodes = MSNode(self.ms)
        self.ms_labels = MSLabel(self.ms)

    @handle_do_errors
    def do_log_level(self, log_level: str):
        """Set the log-level (TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL)."""

        if log_level not in {"TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                f"Invalid format for log_level: '{log_level}', must be one of TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )

        handlers = [
            handler
            for handler in logging.root.handlers
            if isinstance(handler, (logging.StreamHandler, logging.FileHandler))
        ]
        for handler in handlers:
            handler.setLevel(log_level if log_level != "TRACE" else logging.DEBUG)
        self._log.debug("Log level set to %s", log_level)

    def do_exit(self, _arg):
        "Exit the CLI: exit."
        self._log.info("Exiting...")
        return True

    @staticmethod
    def _run_external_shell_command(command, args):
        command_name = "notepad" if os.name == "nt" and command in {"nano", "vi", "vim"} else command
        completed = subprocess.run([command_name, *args], check=False)
        return completed.returncode

    @staticmethod
    def _run_internal_cat(args):
        if not args:
            raise ValueError("Command 'cat' requires at least one path argument.")

        for path in args:
            with open(path, encoding="utf-8", errors="replace") as file:
                sys.stdout.write(file.read())
        return 0

    def _run_shell_command(self, command, args):
        if command == "cd":
            os.chdir(os.path.expanduser(args[0] if args else "~"))
            return 0
        if command == "pwd":
            print(os.getcwd())
            return 0
        if command == "echo":
            print(" ".join(args))
            return 0
        if command == "cat":
            return self._run_internal_cat(args)
        return self._run_external_shell_command(command, args)

    @handle_do_errors
    def do_shell(self, arg):
        """Run allowlisted shell commands only: shell <command> or !<command>."""
        if not arg.strip():
            raise ValueError("No shell command provided.")

        parsed_args = shlex.split(arg, posix=os.name != "nt")
        command, command_args = parsed_args[0], parsed_args[1:]

        normalized_command = _resolve_shell_command(command)
        return self._run_shell_command(normalized_command, command_args)

    def default(self, arg):
        self._log.info("Unknown command: %s", arg)
        self.do_help("")

    @handle_do_errors
    def do_template(self, arg):
        """Create workloads.

        Additional options are listed with -h/--help."""
        return nerve_templates(self, arg, self._log)

    @handle_do_errors
    def do_ms_workloads(self, arg):
        """Manage workloads on the management system.

        Additional options are listed with -h/--help."""
        return ms_workloads(self, arg, self._log)

    @handle_do_errors
    def do_ms_nodes(self, arg):
        """Manage nodes on the management system.

        Additional options are listed with -h/--help."""
        return ms_nodes(self, arg, self._log)

    @handle_do_errors
    def do_ms_labels(self, arg):
        """Manage labels on the management system.

        Additional options are listed with -h/--help."""
        return ms_labels(self, arg, self._log)

    @handle_do_errors
    def do_logout(self, arg):
        """Logout from the management system."""
        self.ms.logout()
        self._log.info("Logged out from the management system.")

    @handle_do_errors
    def do_set_management_system(self, arg):
        """Set a new management system URL.

        Usage: set_management_system <url>
        """

        def args_set_new_management_system(parser):
            parser.add_argument("url", help="Management System URL (e.g., example-ms.nerve.cloud)")
            parser.add_argument(
                "--ms-user",
                default="",
                metavar="USERNAME",
                help=(
                    "Management System login username. Priority: (1) command-line arg, "
                    "(2) credentials.ini, (3) env-var MS_USR"
                ),
            )
            parser.add_argument(
                "--ms-password",
                default="",
                metavar="PASSWORD",
                help=(
                    "Management System login password. Priority: (1) command-line arg, "
                    "(2) credentials.ini, (3) env-var MS_PSW"
                ),
            )

        args = args_interactive(arg, args_set_new_management_system, "Set new Nerve management system URL")
        if not args:
            return 2

        ms_url, ms_user, ms_password = self._get_ms_user_password(args.url, args.ms_user, args.ms_password)
        self.args.ms_url = ms_url
        self.args.ms_user = ms_user
        self.args.ms_password = ms_password

        self.set_ms_url(ms_url, self.args.ms_user, self.args.ms_password)

        if ms_url:
            self._log.info("NerveCLI switched to '%s'", ms_url)
        return 0

    @handle_do_errors
    def do_local_node(self, arg):
        """Manage workloads and docker volumes on a node through its local UI or MS.

        Additional options are listed with -h/--help."""
        return local_node(self, arg, self._log)


def main():
    parser = build_parser()

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(0)

    args = parser.parse_args()
    is_interactive_mode = getattr(args, "func", None) == "cli"
    args.log_level = _log_level_from_verbosity(getattr(args, "verbose", 0), is_interactive_mode)

    if args.store_credentials:
        config = configparser.ConfigParser()
        config.read("credentials.ini")
        if not args.ms_url:
            raise ValueError(
                "MS URL is required to store credentials. Please provide the MS URL with --ms-url."
            )
        if not args.ms_user:
            raise ValueError(
                "MS username is required to store credentials. Please provide the username with --ms-user or set it in the environment variable MS_USR."
            )
        if not args.ms_password:
            raise ValueError(
                "MS password is required to store credentials. Please provide the password with --ms-password or set it in the environment variable MS_PSW."
            )
        if args.ms_url not in config.sections():
            config[args.ms_url] = {}
        if args.ms_user:
            config[args.ms_url]["username"] = args.ms_user
        if args.ms_password:
            config[args.ms_url]["password"] = args.ms_password
        with open("credentials.ini", "w", encoding="utf-8") as configfile:
            config.write(configfile)
        cli_log.info(f"Credentials for {args.ms_url} stored in credentials.ini")

    if not hasattr(args, "func"):
        if not args.store_credentials:
            NerveCLI(args).do_help("")
            raise SystemExit("No sub-command specified")
        cli_log.info("No sub-command specified, but credentials stored successfully. Exiting.")
        sys.exit(0)

    cli = NerveCLI(args)
    if "template" == args.func:
        cli.do_template(args)
    if "ms-workloads" == args.func:
        cli.do_ms_workloads(args)
    if "ms-nodes" == args.func:
        cli.do_ms_nodes(args)
    if "ms-labels" == args.func:
        cli.do_ms_labels(args)
    if "local-node" == args.func:
        cli.do_local_node(args)

    if "cli" == args.func:
        try:
            cli.cmdloop()
        except KeyboardInterrupt:  # pragma: no cover
            print("\nExiting...")

    sys.exit(cli.last_exit_code)


def build_parser():
    # Add initial argurments
    parser = argparse.ArgumentParser(
        description="Nerve API CLI for managing devices, workloads, labels, and remote connections.",
        prog="nerve-cli",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-confirm all prompts (skip interactive confirmations)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them (overrides --yes)",
    )

    ms_settings = parser.add_argument_group("Management System Settings")

    ms_settings.add_argument(
        "--ms-url",
        metavar="URL",
        default="",
        help=(
            "Management System URL (e.g., example-ms.nerve.cloud). Priority: "
            "(1) command-line arg, (2) env-var MS_URL (3) credentials.ini (only if it contains exactly one section)"
        ),
    )
    ms_settings.add_argument(
        "--ms-user",
        metavar="USERNAME",
        help=(
            "Management System login username. Priority: (1) command-line arg, "
            "(2) credentials.ini, (3) env-var MS_USR"
        ),
    )
    ms_settings.add_argument(
        "--ms-password",
        metavar="PASSWORD",
        help=(
            "Management System login password. Priority: (1) command-line arg, "
            "(2) credentials.ini, (3) env-var MS_PSW"
        ),
    )
    parser.add_argument(
        "--work-dir",
        metavar="PATH",
        default=".",
        help="PATH TO working directory for temporary files (default: current directory)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help=(
            "Increase verbosity: -v=INFO, -vv=DEBUG, -vvv=TRACE. Defaults: WARNING for command mode, "
            "INFO for interactive cli mode."
        ),
    )
    parser.add_argument(
        "--store-credentials",
        action="store_true",
        help=("Save credentials to credentials.ini file (security warning: stores plaintext password)"),
    )

    main_subparser = parser.add_subparsers(help="Available subcommands:")

    # cli
    subparser = main_subparser.add_parser("cli", help="Start interactive CLI mode.")
    subparser.set_defaults(func="cli")

    # template
    subparser = main_subparser.add_parser(
        "template",
        help="Generate templates for workload definitions or remote connections.",
    )
    args_templates(subparser)
    subparser.set_defaults(func="template")

    # ms_workloads
    subparser = main_subparser.add_parser(
        "ms-workloads",
        help="Manage workloads on the management system (list, export, provision, delete, deploy).",
    )
    args_ms_workloads(subparser)
    subparser.set_defaults(func="ms-workloads")

    # ms_nodes
    subparser = main_subparser.add_parser(
        "ms-nodes",
        help=(
            "Manage nodes on the management system (list, reboot, workload state, DNA, remote connections), "
            "with filtering support."
        ),
    )
    args_ms_nodes(subparser)
    subparser.set_defaults(func="ms-nodes")

    # ms_labels
    subparser = main_subparser.add_parser("ms-labels", help="Manage labels on the management system.")
    args_ms_labels(subparser)
    subparser.set_defaults(func="ms-labels")

    # local_node
    subparser = main_subparser.add_parser(
        "local-node",
        help="Manage nodes using local API.",
    )
    args_local_node(subparser)
    subparser.set_defaults(func="local-node")
    return parser
