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
import re
import shlex
import sys
from glob import glob

import yaml

_log = logging.getLogger("CLI.utils")


def args_interactive(arg, add_args_function, description):
    if isinstance(arg, argparse.Namespace):
        return arg

    parser = argparse.ArgumentParser(description=description, prog="")
    add_args_function(parser)

    try:
        known, _unknown = parser.parse_known_args(
            args=shlex.split(arg) if isinstance(arg, str) else None,
            namespace=arg if isinstance(arg, argparse.Namespace) else None,
        )
    except SystemExit:
        if isinstance(arg, argparse.Namespace):
            raise
    else:
        return known


def file_write(work_dir, file_name, content, output_methods: list[str] | None = None):
    """Write output file.

    output methods:
    - stdout: print the content to stdout in the specified format (json, yaml, or a specific key)
    - key: print only the value of this key from the content dict to stdout. e.g. 'stdout:name'
        (if content is a list of dicts, print the values of this key for all items, separated by comma)
    - file: write the content to a file in the specified format (json, yaml), default
    - pairs: if content is a dict, print the key:value pairs as comma-separated values (e.g. 'env:production,region:us-west')
    """

    if output_methods is None:
        output_methods = ["file"]
    if (file_name.startswith("stdout:json") or file_name == "stdout") and "stdout" in output_methods:
        print(json.dumps(content, indent=4))
    elif file_name.startswith("stdout:yaml") and "stdout" in output_methods:
        print(yaml.dump(content, indent=4, default_flow_style=False, sort_keys=False))
    elif file_name.startswith("stdout:pairs") and "pairs" in output_methods:
        if isinstance(content, list) and all(
            isinstance(item, dict) and "key" in item and "value" in item for item in content
        ):
            pairs = [f"{label['key']}:{label['value']}" for label in content]
            print(",".join(pairs))
        else:
            raise ValueError(
                "Content must be a dictionary of [{'key':'name', 'value':'name'}, ...] to use 'stdout:pairs' output method."
            )
    elif re.match(r"^stdout:\w+$", file_name) and "key" in output_methods:
        key = file_name.split(":", 1)[1]
        if isinstance(content, dict) and key in content:
            if isinstance(content.get(key), list):
                print(",".join(str(item) for item in content[key]))
            else:
                print(content[key])
        elif isinstance(content, list):
            flat_values = []
            for item in content:
                if isinstance(item, dict) and key in item:
                    value = item[key]
                    if isinstance(value, list):
                        flat_values.extend(str(v) for v in value)
                    else:
                        flat_values.append(str(value))
            if flat_values:
                print(",".join(flat_values))
    else:
        _, file_ext = os.path.splitext(file_name)
        if not file_ext:
            file_name += ".json"
            file_ext = ".json"
        file_path = os.path.abspath(os.path.join(work_dir, file_name))
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as file:
            if file_ext == ".json":
                json.dump(content, file, indent=4)
            elif file_ext in {".yaml", ".yml"}:
                yaml.dump(content, file, indent=4, default_flow_style=False, sort_keys=False)
            else:
                file.write(content)
        _log.info("File '%s' written", file_path)


def file_read(work_dir, file_name, input_methods: list[str] | None = None):  # noqa: PLR0911
    """Read input file.

    input methods:
    - stdin: read the content from stdin in the specified format (json, yaml)
    - name: read the content as a list of dicts with 'name' key, e.g. 'name:node1,node2,node3'
    - serialNumber: read the content as a list of dicts with 'serialNumber' key, e.g. 'serialNumber:SN1,SN2,SN3'
    - _id: read the content as a list of dicts with '_id' key, e.g. '_id:id1,id2,id3'
    - file: read the content from a file in the specified format (json, yaml), default
    - pairs: read the content as comma-separated key:value pairs, e.g. 'env:production,region:us-west'
    """
    if input_methods is None:
        input_methods = ["file"]
        print_source_info = False
    else:
        print_source_info = True
    if file_name in ("stdin:json", "stdin") and "stdin" in input_methods:
        if print_source_info:
            _log.info("Reading content from stdin as JSON")
        return json.load(sys.stdin)
    if file_name == "stdin:yaml" and "stdin" in input_methods:
        if print_source_info:
            _log.info("Reading content from stdin as YAML")
        return yaml.safe_load(sys.stdin)
    if file_name.startswith("name:") and "name" in input_methods:
        ret_val = [{"name": name} for name in file_name.split(":", 1)[1].split(",")]
        if print_source_info:
            _log.info("Reading content from argument converting it to %s", ret_val)
        return ret_val
    if file_name.startswith("serialNumber:") and "serialNumber" in input_methods:
        ret_val = [{"serialNumber": serial} for serial in file_name.split(":", 1)[1].split(",")]
        if print_source_info:
            _log.info("Reading content from argument converting it to %s", ret_val)
        return ret_val
    if file_name.startswith("_id:") and "_id" in input_methods:
        ret_val = [{"_id": id} for id in file_name.split(":", 1)[1].split(",")]
        if print_source_info:
            _log.info("Reading content from argument converting it to %s", ret_val)
        return ret_val
    if file_name.startswith("pairs:") and "pairs" in input_methods:
        pairs_payload = file_name.split(":", 1)[1]
        pairs_list = pairs_payload.split(",")

        # Accept special characters in keys/values, but require every item to be a non-empty key:value pair.
        parsed_pairs = []
        for pair in pairs_list:
            key, sep, value = pair.partition(":")
            if not sep or not key.strip() or not value.strip():
                raise ValueError(
                    f"Invalid key:value pairs format: '{file_name}'. Expected format: "
                    "'pairs:key1:value1,key2:value2'"
                )
            parsed_pairs.append({"key": key, "value": value})

        if print_source_info:
            _log.info("Reading content from argument converting it to %s", parsed_pairs)
        return parsed_pairs

    _, file_ext = os.path.splitext(file_name)
    if not file_ext:
        file_name += ".json"
        file_ext = ".json"
    file_path = os.path.abspath(os.path.join(work_dir, file_name))
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File '{file_path}' does not exist")
    if print_source_info:
        _log.info("Reading content from file '%s'", file_path)
    with open(file_path, "r", encoding="utf-8") as file:
        if file_ext == ".json":
            return json.load(file)
        if file_ext in {".yaml", ".yml"}:
            return yaml.safe_load(file)
        return file.read()


def resolve_workload_file_paths(work_dir: str, path_expression: str) -> list[str]:
    """Resolve comma-separated paths (including wildcards) to absolute file paths."""
    resolved_paths = []
    for path_item in path_expression.split(","):
        normalized_path = path_item.strip()
        if not normalized_path:
            continue

        raw_pattern = (
            normalized_path if os.path.isabs(normalized_path) else os.path.join(work_dir, normalized_path)
        )
        expanded_paths = [os.path.abspath(path) for path in glob(raw_pattern)]

        # Keep explicit non-glob paths so callers can still report missing files clearly.
        if not expanded_paths and not any(char in normalized_path for char in "*?[]"):
            expanded_paths = [os.path.abspath(raw_pattern)]

        resolved_paths.extend(expanded_paths)

    return sorted(resolved_paths)


def clean_wl_definition(wl_def):
    """Clean the workload definition by removing provision specific elements."""
    to_be_removed = [
        "_id",
        "createdAt",
        "createdBy",
        "updatedAt",
    ]
    if not isinstance(wl_def, dict):
        return wl_def

    cleaned_def = wl_def.copy()
    for k in to_be_removed:
        cleaned_def.pop(k, None)

    version_keys_to_be_removed = {
        "_id",
        "hash",
        "createdAt",
        "createdBy",
        "updatedAt",
        "isDownloading",
        "isDeployable",
        "summarizedFileStatuses",
        "numberOfServices",
        "export",
        "numberOfFiles",
        "overall_size",
    }
    if "versions" in cleaned_def:
        for version in cleaned_def["versions"]:
            for k in version_keys_to_be_removed:
                version.pop(k, None)
    return cleaned_def


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


def ask_for_confirmation(args, prompt):
    """Ask the user for confirmation and return True if the answer is yes."""

    if args.dry_run:
        _log.info("Option '--dry-run' is set. Will not perform any action on the node or management system.")
        return False

    if args.yes:
        return True

    response = input(f"{prompt} (y/n): ")
    return response.lower() == "y"
