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

import gzip
import os
import shutil
import tarfile
from contextlib import closing

from .utils import ask_for_confirmation
from .utils import clean_wl_definition
from .utils import file_write


def get_workload_rel_path(work_dir, path, workload_name, workload_version):
    """Get the path for storing the workloads files."""
    replace_chars = ["/", " ", ":", ".", "(", ")", "@"]  # characters to replace in workload name and version
    for char in replace_chars:
        workload_name = workload_name.replace(char, "_")
        workload_version = workload_version.replace(char, "_")

    full_path = os.path.join(work_dir, path, workload_name, workload_version)
    return os.path.relpath(full_path, work_dir)


def create_ms_workloads_path(work_dir, path, workload_name, workload_version):
    """Create the path for storing the workloads files."""
    rel_path = get_workload_rel_path(work_dir, path, workload_name, workload_version)
    full_path = os.path.join(work_dir, rel_path)
    if not os.path.exists(full_path):
        os.makedirs(full_path)
    return full_path


def reorder_wl_def_files(wl_definition: dict) -> tuple[dict, bool]:
    """Move all XML file entries to the end if non-XML files are present.
    Returns the potentially modified wl_definition and whether the file order changed.
    """
    versions = wl_definition.get("versions")
    if not isinstance(versions, list) or not versions:
        return wl_definition

    files = versions[0].get("files")
    if not isinstance(files, list) or len(files) < 2:  # noqa: PLR2004
        return wl_definition

    def is_xml_file(file_entry: dict) -> bool:
        file_name = (file_entry.get("originalName") or file_entry.get("name") or "").lower()
        return file_name.endswith(".xml")

    xml_files = [file_entry for file_entry in files if is_xml_file(file_entry)]
    non_xml_files = [file_entry for file_entry in files if not is_xml_file(file_entry)]

    # Reorder only when both groups exist; keep relative order within each group.
    if not xml_files or not non_xml_files:
        return wl_definition

    reordered_files = non_xml_files + xml_files
    changed = reordered_files != files
    if changed:
        versions[0]["files"] = reordered_files

    return wl_definition


def ms_workloads_single_export(ms_workloads, args, wl_name, filtered_versions, log):
    if not filtered_versions:
        log.info("No versions found for workload '%s', skipping export", wl_name)
        return

    # retrieve all workload version details and overwrite the filtered versions
    for i, version in enumerate(filtered_versions):  # noqa: PLR1702
        if not version.get("releaseName"):
            version.update({"releaseName": ""})

        wl_version = ms_workloads.WorkloadVersion(wl_name, version["name"], version.get("releaseName"))
        wl_def_content = wl_version.get_container()
        detailed_version = wl_def_content.get("versions")[0]
        filtered_versions[i] = detailed_version

        release_version = (
            f"_{detailed_version.get('releaseName', '')}" if detailed_version.get("releaseName") else ""
        )
        save_path = create_ms_workloads_path(
            args.work_dir, args.export, wl_name, f"{detailed_version['name']}{release_version}"
        )
        log.info(
            "Exporting workload '%s' with version '%s' to '%s'",
            wl_name,
            detailed_version["name"],
            os.path.join(
                args.work_dir,
                get_workload_rel_path(args.work_dir, args.export, wl_name, detailed_version["name"]),
            ),
        )

        if wl_def_content["type"] == "vm":
            wl_def_content = reorder_wl_def_files(wl_def_content)
        file_write(save_path, "wl_def.json", clean_wl_definition(wl_def_content))

        if wl_def_content["type"] == "docker-compose":
            compose_name = next(
                (entry for entry in wl_def_content["versions"][0]["files"] if entry["type"] == "compose"), {}
            ).get("originalName", None)
            if not compose_name:
                log.warning(
                    "No compose file found in workload '%s' version '%s'. Skipping compose file export.",
                    wl_name,
                    detailed_version["name"],
                )
            else:
                compose_file = wl_version.get_compose_content()
                file_write(save_path, compose_name, compose_file)

        if args.template:
            continue

        with closing(wl_version.export_workload_version()) as response:
            file_name = (
                response.headers
                .get("Content-Disposition", "attachment; filename=workload_file")
                .split("filename=")[-1]
                .strip('"')
            )

            destination_path = os.path.join(save_path, file_name)
            if os.path.exists(destination_path):
                destination_path = os.path.join(save_path, file_name)

            # Save the file to the specified path in chunks to handle large files
            with open(destination_path, "wb") as dest_file:
                for chunk in response.iter_content(chunk_size=8192):  # Stream in 8KB chunks
                    if chunk:  # Filter out keep-alive new chunks
                        dest_file.write(chunk)
        log.debug("Downloaded and saved file: '%s'", file_name)
        # untar the file
        files_contained = []
        if file_name.endswith((".tar.gz", ".tgz")):
            log.debug("Extracting tar-gzipped file: '%s' ('%s')", destination_path, file_name)
            with tarfile.open(destination_path, "r:gz") as tar:
                tar.extractall(path=save_path)
                files_contained = tar.getnames()
            log.debug("Extracted files: '%s'", files_contained)
        if file_name.endswith(".tar"):
            with tarfile.open(destination_path, "r:") as tar:
                tar.extractall(path=save_path)
                files_contained = tar.getnames()
            log.debug("Extracted files: '%s'", files_contained)
        os.remove(destination_path)
        for file in files_contained:
            if file.endswith(".gz"):
                full_file_path = os.path.join(save_path, file)
                log.debug("Extracting gzipped file: '%s' ('%s')", full_file_path, file)
                extracted_file = os.path.splitext(full_file_path)[0]
                with gzip.open(full_file_path, "rb") as f_in, open(extracted_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                log.debug("Extracted gzipped file: '%s'", extracted_file)
                os.remove(full_file_path)

        for file_info in wl_def_content["versions"][0].get("files", []):
            name = (
                file_info["name"].rsplit(".gz", 1)[0]
                if file_info["name"].endswith(".gz")
                else file_info["name"]
            )
            original_name = file_info["originalName"]
            # for docker registry workloads
            if original_name.startswith("registry/"):
                original_name = os.path.basename(original_name).split(":", -1)[0] + file_info.get(
                    "type", ".tar"
                )
            # move file with name to original name
            if (
                name
                and original_name
                and name != original_name
                and os.path.exists(os.path.join(save_path, name))
            ):
                os.rename(
                    os.path.join(save_path, name),
                    os.path.join(save_path, original_name),
                )
                log.debug("Renamed file '%s' to '%s'", name, original_name)
                log.info("Saved file '%s'", os.path.join(save_path, original_name))
            elif name and not original_name and os.path.exists(os.path.join(save_path, name)):
                log.debug("File '%s' has no original name specified in the JSON", name)
                if file_info["source"]:
                    original_name = file_info["source"].split("/")[-1].split(":")[0]
                    if "." in name:
                        if name.endswith(".gz"):
                            file_suffix = "." + name.split(".")[-2] + "." + name.split(".")[-1]
                        else:
                            file_suffix = "." + name.split(".")[-1]
                    else:
                        file_suffix = ""
                    log.debug("Trying to rename file '%s' to '%s' based on source", name, original_name)
                    if file_suffix:
                        os.rename(
                            os.path.join(save_path, name),
                            os.path.join(save_path, original_name + file_suffix),
                        )
                        log.debug("Renamed file '%s' to '%s'", name, original_name + file_suffix)
                        log.info("Saved file '%s'", os.path.join(save_path, original_name + file_suffix))
                    else:
                        log.debug(
                            "Could not determine file suffix for file '%s', keeping the name as is", name
                        )
                        log.info("Saved file '%s'", os.path.join(save_path, name))
            elif os.path.exists(os.path.join(save_path, name)):
                log.info("Saved file '%s'", os.path.join(save_path, name))
            else:
                log.warning(
                    "File '%s' not found in the extracted files for workload '%s' version '%s'",
                    name,
                    wl_name,
                    detailed_version["name"],
                )


def ms_workloads_export(ms_workloads, workloads, args, log=None):
    num_versions = sum(len(workload.get("versions", [])) for workload in workloads)
    export_path = os.path.abspath(os.path.join(args.work_dir, args.export))
    if num_versions == 0:
        log.error("No workload versions found to export with the provided filters")
        return 1
    perform_action = ask_for_confirmation(
        args,
        (
            f"Are you sure you want to export {num_versions} workload versions?"
            f" This will download the workload files and their details to {export_path}/<workload-name>/<version-name>."
        ),
    )
    for workload in workloads:
        wl_name = workload["name"]
        if not perform_action:
            for version in workload["versions"]:
                log.info(
                    "Skipping export of workload '%s' version '%s' to '%s'",
                    wl_name,
                    version["name"],
                    os.path.join(
                        args.work_dir,
                        get_workload_rel_path(args.work_dir, args.export, wl_name, version["name"]),
                    ),
                )
            continue
        ms_workloads_single_export(ms_workloads, args, wl_name, workload["versions"], log)
    return 0
