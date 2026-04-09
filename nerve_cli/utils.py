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


"""Functions to support cli commands."""

import argparse
import json
import logging
import os
import posixpath
import re

import docker
import yaml

_log = logging.getLogger("CLI.utils")


def check_filter_arg(cmd_line_filter, data_value):
    """Check if the argument is a filter and return the filter.
    If cmd_line_filter is not defined, return True."""

    if not cmd_line_filter:
        return True
    ret_val = False

    if cmd_line_filter:
        if isinstance(cmd_line_filter, (bool, int)):
            ret_val = cmd_line_filter == data_value
        elif cmd_line_filter.startswith("regex:"):
            if isinstance(data_value, str):
                regex = re.compile(cmd_line_filter[6:])
                ret_val = bool(regex.search(data_value))
        else:
            ret_val = cmd_line_filter == data_value

    return ret_val


def args_interactive(arg, add_args_function, description):
    parser = argparse.ArgumentParser(description=description, prog="")
    add_args_function(parser)

    # For adding argument from initial start of cli
    parser.add_argument("--ms_user", default="")
    parser.add_argument("--ms_password", default="")
    parser.add_argument("--work_dir", default="work_dir")

    try:
        known, _unknown = parser.parse_known_args(
            args=arg.split() if isinstance(arg, str) else None,
            namespace=arg if isinstance(arg, argparse.Namespace) else None,
        )
    except SystemExit:
        if isinstance(arg, argparse.Namespace):
            raise
    else:
        return known


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
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File '{file_path}' does not exist")
    _log.debug("Reading file: %s", file_path)
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
        "export",
        "updatedAt",
        "numberOfFiles",
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


def docker_registry_workflow(work_dir, file_paths, repository, tag="latest"):
    try:  # noqa: PLR1702
        client = docker.from_env()
        for file_path in file_paths:
            if (
                file_path.endswith((".tar", ".tar.gz"))
                and file_path.split("/")[-1].split(".")[0] in repository
            ):
                with open(os.path.join(work_dir, file_path), "rb") as f:
                    images = client.images.load(f.read())
                    loaded_image = images[0]
                    if loaded_image.tag(repository, tag=tag):
                        _log.debug("Image tagged as %s:%s", repository, tag)
                    prev_status = ""
                    for line in client.images.push(repository, tag=tag, stream=True, decode=True):
                        if prev_status != line.get("status"):
                            _log.info(
                                "%s:%s - %s %s",
                                repository,
                                tag,
                                line.get("status", ""),
                                line.get("progress", ""),
                            )
                            prev_status = line.get("status")
                    client.images.remove(image=f"{repository}:{tag}", force=True)
    except Exception as e:
        _log.info("Make sure Docker is installed and running and you are logged in to the correct registry.")
        _log.info(
            "You can also try to push the image manually using 'docker load' and 'docker push' commands."
        )
        raise RuntimeError(f"Error occurred while processing Docker images: {e}")


def format_size_string(size_bytes, fraction_digits=2):
    """Format the size in bytes to a human-readable string."""
    if size_bytes > 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.{fraction_digits}f}GB"
    if size_bytes > 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.{fraction_digits}f}MB"
    if size_bytes > 1024:  # noqa: PLR2004
        return f"{size_bytes / 1024:.{fraction_digits}f}KB"
    return f"{size_bytes}B"


def size_string_to_bytes(size_str):
    """Convert a human-readable size string to bytes."""
    size_str = size_str.strip().upper()
    if size_str.endswith("GB"):
        return int(float(size_str[:-2]) * 1024 * 1024 * 1024)
    if size_str.endswith("MB"):
        return int(float(size_str[:-2]) * 1024 * 1024)
    if size_str.endswith("KB"):
        return int(float(size_str[:-2]) * 1024)
    if size_str.endswith("B"):
        return int(size_str[:-1])
    raise ValueError(f"Invalid size string: {size_str}")
