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


"""Functions to support cli commands."""

import argparse
import json
import logging
import os
import posixpath
import re

import yaml

_log = logging.getLogger("cli_utils")


def check_filter_arg(cmd_line_filter, data_value):
    """Check if the argument is a filter and return the filter.
    If cmd_line_filter is not defined, return True."""

    if cmd_line_filter == "" or cmd_line_filter is None:
        return True
    ret_val = False

    if cmd_line_filter:
        if isinstance(cmd_line_filter, bool):
            ret_val = cmd_line_filter == data_value
        elif isinstance(cmd_line_filter, int):
            ret_val = cmd_line_filter == data_value
        elif cmd_line_filter.startswith("regex:"):
            if isinstance(data_value, str):
                regex = re.compile(cmd_line_filter[6:])
                ret_val = bool(regex.search(data_value))
        else:
            ret_val = cmd_line_filter == data_value

        _log.debug("Filtering data '%s' with filter '%s' -> %s", data_value, cmd_line_filter, ret_val)
    return ret_val


def args_interactive(arg, add_args_function, description):
    parser = argparse.ArgumentParser(description=description, prog="")
    add_args_function(parser)

    try:
        known, _unknown = parser.parse_known_args(
            args=arg.split() if isinstance(arg, str) else None,
            namespace=arg if isinstance(arg, argparse.Namespace) else None,
        )
        return known
    except SystemExit:
        if isinstance(arg, argparse.Namespace):
            raise
        # Handle the case where the parser would normally exit
        pass
    return None


def file_write(work_dir, file_name, content):
    _, file_ext = os.path.splitext(file_name)
    if not file_ext:
        file_name += ".json"
        file_ext = ".json"
    file_path = posixpath.join(work_dir, file_name)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as file:
        if file_ext == ".json":
            json.dump(content, file, indent=4)
        elif file_ext in {".yaml", ".yml"}:
            yaml.dump(content, file, indent=4, default_flow_style=False)
        else:
            file.write(content)
    _log.info("File '%s' written", file_path)
    return file_path


def file_append(work_dir, file_name, content):
    _, file_ext = os.path.splitext(file_name)
    if not file_ext:
        file_name += ".json"
        file_ext = ".json"
    file_path = posixpath.join(work_dir, file_name)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "a", encoding="utf-8") as file:
        if file_ext == ".json":
            json.dump(content, file, indent=4)
        elif file_ext in {".yaml", ".yml"}:
            yaml.dump(content, file, indent=4, default_flow_style=False)
        else:
            file.write(content)
    _log.info("File '%s' extended", file_path)
    return file_path


def file_read(work_dir, file_name):
    _, file_ext = os.path.splitext(file_name)
    if not file_ext:
        file_name += ".json"
        file_ext = ".json"
    file_path = posixpath.join(work_dir, file_name)
    _log.debug("Reading file: %s", file_path)
    if not os.path.exists(file_path):
        return None
    with open(file_path, "r", encoding="utf-8") as file:
        if file_ext == ".json":
            return json.load(file)
        if file_ext in {".yaml", ".yml"}:
            return yaml.safe_load(file)
        return file.read()

def clean_wl_definition(wl_def):
    """Clean the workload definition by removing provision specific elements."""
    to_be_removed = [
        "createdBy",
        "_id",
        "createdAt",
        "hash",
        "isDeployable",
        "overall_size",
        "summarizedFileStatuses",
        "numberOfServices",
    ]
    if not isinstance(wl_def, dict):
        return wl_def
    cleaned_def = {}
    for k, v in wl_def.items():
        if k not in to_be_removed:
            if isinstance(v, dict):
                cleaned_def[k] = clean_wl_definition(v)
            elif isinstance(v, list):
                cleaned_def[k] = [clean_wl_definition(item) if isinstance(item, dict) else item for item in v]
            else:
                cleaned_def[k] = v
        else:
            _log.debug("Removing key '%s' from workload definition", k)
    return cleaned_def
