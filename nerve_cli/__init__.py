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

"""Command line interface for nerve_lib API."""

import argparse
import cmd
import configparser
import logging
import os
import sys
import json
import requests

from nerve_lib import MSHandle
from nerve_lib import MSLabel
from nerve_lib import MSNode
from nerve_lib import MSWorkloads
from nerve_lib import setup_logging
from nerve_lib import CheckStatusCodeError

from .labels import args_labels
from .labels import labels
from .ms_workloads import args_ms_workloads
from .ms_workloads import ms_workloads
from .nodes_dna import args_nodes_dna
from .nodes_dna import nodes_dna
from .service_os_dna import args_service_os_dna
from .service_os_dna import service_os_dna
from .nodes_list import args_nodes_list
from .nodes_list import nodes_list
from .nodes_reboot import args_nodes_reboot
from .nodes_reboot import nodes_reboot
from .nodes_remote_connections import args_nodes_remote_connections
from .nodes_remote_connections import nodes_remote_connections
from .nodes_workloads_state import args_nodes_workloads_state
from .nodes_workloads_state import nodes_workloads_state
from .workload_create import args_workload_create
from .workload_create import workload_create



setup_logging(compact = True)# format_string="{levelname:<7} :: {message}")
cli_log = logging.getLogger("NerveCLI")


class NerveCLI(cmd.Cmd):
    intro = "Welcome to the nerve_lib CLI. Type help or ? to list commands.\n"
    prompt = "(nerve) "

    def __init__(self, ms_url="", ms_user="", ms_password="", work_dir="work_dir", log_level="INFO"):
        super().__init__()

        self._log = logging.getLogger("NerveCLI")
        self.do_log_level(log_level)

        self._set_login(ms_url, ms_user, ms_password)
        self.work_dir = work_dir
        os.makedirs(self.work_dir, exist_ok=True)

        if self.ms_url:
            self.ms = MSHandle(self.ms_url, self.ms_user, self.ms_password)
        else:
            # usage of MS handle will lead to an error if no MS URL is provided
            # Error is only raised when MS actually needs be be used, function not requiring this call (e.g. to create templates)
            # will work without MS URL
            class FakeCallMS:
                def __init__(self, *args, **kwargs):
                    pass

                # any function call not defined shall lead to an error
                def __getattr__(self, _name):
                    raise ValueError(
                        "No MS URL provided. Please provide the MS URL in the environment"
                        " variable MS_URL or as an argument."
                        "If a credentials.ini file exists with only one section, the MS will be set to this."
                    )
            self.ms = FakeCallMS()

        self.ms_workloads = MSWorkloads(self.ms)

        self.ms_nodes = MSNode(self.ms)
        self.ms_labels = MSLabel(self.ms)

        self._log.info("NerveCLI started for '%s'", self.ms_url)

    def _set_login(self, ms_url, ms_user, ms_password):
        config = configparser.ConfigParser()
        config.read("credentials.ini")

        if not ms_url:
            ms_url_from_credentials = ""
            if len(config.sections()) == 1:
                ms_url_from_credentials = config.sections()[0]
            self.ms_url = os.environ.get("MS_URL") or ms_url_from_credentials
            if not self.ms_url:
                return
        elif ms_url.startswith("http"):
            self.ms_url = ms_url.split("://")[1]
        else:
            self.ms_url = ms_url

        if not ms_user or not ms_password:
            # check if the section 'ms_url' exists
            if self.ms_url in config.sections():
                self._log.debug("Using credentials from credentials.ini for %s", self.ms_url)
                if not ms_user:
                    ms_user = config[self.ms_url]["username"]
                if not ms_password:
                    ms_password = config[self.ms_url]["password"]
            elif (not os.environ.get("MS_USR") and not ms_user) or (
                not os.environ.get("MS_PSW") and not ms_password
            ):
                self._log.warning(
                    "No credentials provided for MS. Please provide credentials in the environment"
                    " variables MS_USR and MS_PSW or in the credentials.ini file."
                )
            else:
                self._log.debug("Using credentials from environment variables for %s", self.ms_url)
                ms_user = os.environ.get("MS_USR")
                ms_password = os.environ.get("MS_PSW")

        self.ms_user = ms_user
        self.ms_password = ms_password

    def do_log_level(self, arg):
        """Set the log-level (DEBUG, INFO, WARNING, ERROR, CRITICAL)."""

        if arg not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            self._log.warning("Invalid log-level: %s", arg)
            return
        
        handlers = [
            handler for handler in logging.root.handlers if isinstance(handler, logging.StreamHandler) or isinstance(handler, logging.FileHandler)
        ]
        for handler in handlers:
            handler.setLevel(arg)

    def do_exit(self, arg):
        "Exit the CLI: exit."
        self._log.info("Exiting...")
        return True

    def default(self, line):
        self._log.info("Unknown command: %s", line)

    def do_nodes_list(self, arg):
        """List nodes.

        Addtional options are listed with -h/--help."""
        nodes_list(self.ms_nodes, self.work_dir, arg)

    def do_workload_create(self, arg):
        """Create workloads.

        Addtional options are listed with -h/--help."""
        workload_create(self.ms_workloads, self.work_dir, arg)

    def do_ms_workloads(self, arg):
        """List workloads on MS.

        Addtional options are listed with -h/--help."""
        ms_workloads(self.ms_workloads, self.ms_nodes, self.work_dir, arg)

    def do_nodes_reboot(self, arg):
        """Reboot nodes.

        Addtional options are listed with -h/--help."""
        nodes_reboot(self.ms_nodes, self.work_dir, arg)

    def do_nodes_dna(self, arg):
        """Nodes DNA functions.

        Addtional options are listed with -h/--help."""
        nodes_dna(self.ms_nodes, self.work_dir, arg)

    def do_service_os_dna(self, arg):
        """Nodes DNA functions.

        Addtional options are listed with -h/--help."""
        service_os_dna(self.ms_nodes, self.work_dir, arg)

    def do_nodes_workloads_state(self, arg):
        """Change the state of all workloads listed in the nodes file.

        Addtional options are listed with -h/--help."""
        nodes_workloads_state(self.ms_nodes, self.work_dir, arg)

    def do_nodes_remote_connections(self, arg):
        """Manage remote connections from nodes.

        Addtional options are listed with -h/--help."""
        nodes_remote_connections(self.ms_nodes, self.work_dir, arg)

    def do_labels(self, arg):
        """Manage labels on the management system.

        Addtional options are listed with -h/--help."""
        labels(self.ms_labels, self.work_dir, arg)

    def do_logout(self):
        """Logout from the management system."""
        self.ms.logout()
        self._log.info("Logged out from the management system.")

def main():
    setup_logging(compact=True)

    # Add initial argurments
    parser = argparse.ArgumentParser(
        description="Nerve API CLI for deploying applications to devices.", prog="nerve-cli"
    )

    ms_settings = parser.add_argument_group("Management System Settings")

    ms_settings.add_argument(
        "--ms_url",
        metavar="<MS_url>",
        default="",
        help="Url of the Nerve MS. If a credentials.ini file exists with only one section, the MS will be set to this  (default to env-var MS_URL)",
    )
    ms_settings.add_argument(
        "--ms_user",
        metavar="<MS_username>",
        help="Login user for Nerve MS (user is read from credentials.ini file or defaults to env-var MS_USR)",
    )
    ms_settings.add_argument(
        "--ms_password",
        metavar="<MS_password>",
        help="Login password for Nerve MS (password is read from credentials.ini file or defaults to env-var MS_PSW)",
    )
    parser.add_argument(
        "--work_dir",
        metavar="<directory>",
        default="work_dir",
        help="Directory to store temporary files (defaults to work_dir)",
    )
    parser.add_argument(
        "--log_level",
        default="INFO",
        help="Set the log level (default: INFO)",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    parser.add_argument(
        "--store_credentials",
        action="store_true",
        help="Store the provided credentials in the credentials.ini file for future use",
    )

    main_subparser = parser.add_subparsers(help="Available sub-commands:")

    # cli
    subparser = main_subparser.add_parser("cli", help="Start the interactive CLI")
    subparser.set_defaults(func="cli")

    # workload_create
    subparser = main_subparser.add_parser(
        "workload_create",
        help="Create a new workload on the management system. An option allows to create a template.",
    )
    args_workload_create(subparser)
    subparser.set_defaults(func="workload_create")

    # ms_workloads
    subparser = main_subparser.add_parser(
        "ms_workloads",
        help="Create a workloads json file based on filter options, and perform actions on these workloads like deploy or delete.",
    )
    args_ms_workloads(subparser)
    subparser.set_defaults(func="ms_workloads")

    # nodes_list
    subparser = main_subparser.add_parser(
        "nodes_list", help="Create a nodes json file based on different filter options."
    )
    args_nodes_list(subparser)
    subparser.set_defaults(func="nodes_list")

    # nodes_reboot
    subparser = main_subparser.add_parser("nodes_reboot", help="Reboot nodes")
    args_nodes_reboot(subparser)
    subparser.set_defaults(func="nodes_reboot")

    # nodes_dna
    subparser = main_subparser.add_parser("nodes_dna", help="Nodes DNA functions")
    args_nodes_dna(subparser)
    subparser.set_defaults(func="nodes_dna")

    # service_os_dna
    subparser = main_subparser.add_parser("service_os_dna", help="Service OS DNA functions")
    args_service_os_dna(subparser)
    subparser.set_defaults(func="service_os_dna")

    # nodes_workloads_state
    subparser = main_subparser.add_parser(
        "nodes_workloads_state", help="Change the state of all workloads listed in the nodes file"
    )
    args_nodes_workloads_state(subparser)
    subparser.set_defaults(func="nodes_workloads_state")

    # nodes_remote_connections
    subparser = main_subparser.add_parser("nodes_remote_connections", help="Manage remote tunnels from nodes")
    args_nodes_remote_connections(subparser)
    subparser.set_defaults(func="nodes_remote_connections")

    # labels
    subparser = main_subparser.add_parser("labels", help="Manage labels on the management system")
    args_labels(subparser)
    subparser.set_defaults(func="labels")

    subparser = main_subparser.add_parser("logout", help="Logout from the management system")
    subparser.set_defaults(func="logout")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(0)

    args = parser.parse_args()

    if args.store_credentials:
        config = configparser.ConfigParser()
        config.read("credentials.ini")
        if args.ms_url not in config.sections():
            config[args.ms_url] = {}
        if args.ms_user:
            config[args.ms_url]["username"] = args.ms_user
        if args.ms_password:
            config[args.ms_url]["password"] = args.ms_password
        with open("credentials.ini", "w") as configfile:
            config.write(configfile)
        cli_log.info(f"Credentials for {args.ms_url} stored in credentials.ini")

    if not hasattr(args, "func"):
        raise SystemExit("No sub-command specified")
    
    try:
        cli = NerveCLI(args.ms_url, args.ms_user, args.ms_password, args.work_dir, args.log_level)
        if "workload_create" == args.func:
            cli.do_workload_create(args)
        if "ms_workloads" == args.func:
            cli.do_ms_workloads(args)
        if "nodes_list" == args.func:
            cli.do_nodes_list(args)
        if "nodes_reboot" == args.func:
            cli.do_nodes_reboot(args)
        if "nodes_dna" == args.func:
            cli.do_nodes_dna(args)
        if "service_os_dna" == args.func:
            cli.do_service_os_dna(args)
        if "nodes_workloads_state" == args.func:
            cli.do_nodes_workloads_state(args)
        if "nodes_remote_connections" == args.func:
            cli.do_nodes_remote_connections(args)
        if "labels" == args.func:
            cli.do_labels(args)
        if "logout" == args.func:
            cli.do_logout()
    except Exception as ex_msg:
        error = {
            "dns": "Name or service not known",
            "404": "404 Not Found",
            "invalid_credentials": "Invalid credentials",
            "provide_credentials": "No username/password provided for MS login",
            "no_ms_url": "No MS URL provided.",
        }
        emsg = "An error occured: "
        print_trace = False
        if isinstance(ex_msg, requests.exceptions.ConnectionError):
            if error["dns"] in str(ex_msg):
                emsg = "The URL of the Management System could not be resolved"
            else:
                emsg = f"Failed to connect to Management System: {ex_msg}"
        elif isinstance(ex_msg, ValueError):
            for err_key in ["provide_credentials", "no_ms_url"]:
                if error[err_key] in str(ex_msg):
                    emsg = str(ex_msg)
                    break
            else:
                print_trace = True
        elif error["404"] in str(ex_msg):
            emsg = "The URL either does not exist or it does not point to a Nerve Management System"
        elif error["invalid_credentials"] in str(ex_msg):
            emsg = "Failed to authorize (invalid credentials). Please check your credentials"
        elif isinstance(ex_msg, CheckStatusCodeError):
            pass  # do not print trace for status code errors
        else:
            print_trace = True

        cli_log.error(emsg)
        if print_trace:
            cli_log.exception(ex_msg)

    if "cli" == args.func:
        try:
            cli.cmdloop()
        except KeyboardInterrupt:  # pragma: no cover
            print("\nExiting...")