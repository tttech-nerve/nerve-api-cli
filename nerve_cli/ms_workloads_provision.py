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

import json
import os
import tarfile

import docker
import requests
from nerve_lib import CheckStatusCodeError

from .utils import ask_for_confirmation
from .utils import clean_wl_definition
from .utils import file_read
from .utils import file_write
from .utils import resolve_workload_file_paths


def get_workload_rel_path(work_dir, path, workload_name, workload_version):
    """Get the path for storing the workloads files."""
    replace_chars = ["/", " ", ":", ".", "(", ")", "@"]  # characters to replace in workload name and version
    for char in replace_chars:
        workload_name = workload_name.replace(char, "_")
        workload_version = workload_version.replace(char, "_")

    full_path = os.path.join(work_dir, path, workload_name, workload_version)
    return os.path.relpath(full_path, work_dir)


def parse_docker_compose_for_images(work_dir, yml_path):
    """Parse the Docker Compose file to extract repository and tag information from 'image' keys."""
    data = file_read(work_dir, yml_path)
    images = []
    if "services" in data:
        for service in data["services"].values():
            if "image" in service:
                image = service["image"]
                if ":" in image:
                    repo, tag = image.rsplit(":", 1)
                else:
                    repo = image
                    tag = "latest"
                images.append((repo, tag))
    return images


def modify_docker_compose_file(work_dir, docker_compose_path, target_url, internal_docker_registry):
    """Modify the Docker Compose file with updated image URLs."""
    data = file_read(work_dir, docker_compose_path)
    if "services" in data:
        for service in data["services"].values():
            if "image" in service:
                image = service["image"]
                if "/registry/" in image and internal_docker_registry:
                    # To convert image_url from one MS to another
                    repo_part = image.split("/registry/")[0]
                    service["image"] = image.replace(repo_part, target_url, 1)
                elif internal_docker_registry:
                    # To convert image_url to internal registry
                    service["image"] = target_url + "/registry/" + image
                elif "/registry/" in image:
                    # To convert image_url to legacy storage
                    service["image"] = image.split("/registry/")[-1]
    file_write(work_dir, docker_compose_path, data)


def modify_wl_def_registry_type(wl_def, args, log):
    if wl_def["type"] not in {"docker-compose", "docker"}:
        return wl_def

    if args.registry and wl_def["internalDockerRegistry"] == False:
        log.info(
            "Modifying workload definition to set 'internalDockerRegistry' to True for registry workload"
        )
        wl_def["internalDockerRegistry"] = True

        if wl_def["type"] == "docker":
            wl_def.pop("deleted", None)
            for version in wl_def["versions"]:
                if "workloadSpecificProperties" not in version:
                    version["workloadSpecificProperties"] = version["workloadProperties"].copy()
                    version.pop("workloadProperties", None)
                version.pop("deleted", None)
                version.pop("releaseName", None)
                version.pop("dockerFileOption", None)
                version.pop("dockerFilePath", None)
                version.pop("restartOnConfigurationUpdate", None)
                version.pop("firstVolumeAsConfigurationStorage", None)
                version.pop("capabilities", None)

    if args.legacy and wl_def["internalDockerRegistry"] == True:
        log.info("Modifying workload definition to set 'internalDockerRegistry' to False for legacy workload")
        wl_def["internalDockerRegistry"] = False

        if wl_def["type"] == "docker":
            for version in wl_def["versions"]:
                if "workloadProperties" not in version:
                    version["workloadProperties"] = version["workloadSpecificProperties"].copy()
                    version.pop("workloadSpecificProperties", None)

    return wl_def


def get_repotags_from_docker_tar(work_dir, file_path, log):
    repo_tags = ""

    open_method = "r:gz" if file_path.endswith(".tar.gz") else "r"
    while True:  # noqa: PLR1702
        try:  # noqa: PLW0717
            with tarfile.open(os.path.join(work_dir, file_path), open_method) as tar_file:
                for member in tar_file.getmembers():
                    if member.name == "manifest.json":
                        extracted_member = tar_file.extractfile(member)
                        if extracted_member is None:
                            continue
                        with extracted_member as manifest_file:
                            manifest = json.load(manifest_file)
                        repo_tags = manifest[-1].get("RepoTags", ["None"])
                        break

                    if member.name.endswith(".tar.gz"):
                        extracted_member = tar_file.extractfile(member)
                        if extracted_member is None:
                            continue
                        with (
                            extracted_member as nested_tar_stream,
                            tarfile.open(fileobj=nested_tar_stream, mode="r:gz") as file_inside,
                        ):
                            for json_file in file_inside.getmembers():
                                if json_file.name == "manifest.json":
                                    manifest_member = file_inside.extractfile(json_file)
                                    if manifest_member is None:
                                        continue
                                    with manifest_member as manifest_file:
                                        manifest = json.load(manifest_file)
                                    repo_tags = manifest[-1].get("RepoTags", ["None"])
                                    break
        except tarfile.ReadError as ex_msg:
            if "not a gzip file" in str(ex_msg):
                log.warning(
                    "File '%s' is not a gzip file, trying to open it as a regular tar archive", file_path
                )
                open_method = "r"
                continue
            raise
        break
    return repo_tags


def push_workload_to_docker_registry(
    work_dir, file_paths, dest_ms_url, repository, tag="latest", ms_usr: str = "", ms_psw: str = "", log=None
):
    client = None
    try:  # noqa: PLW0717
        file_tags = {}
        for file_path in file_paths:
            if file_path.endswith((".tar", ".tar.gz")):
                # Skip files that do not contain the specified tag in their manifest to avoid unnecessary processing
                file_tags[file_path] = get_repotags_from_docker_tar(work_dir, file_path, log)[0]
                if repository.split("/", -1)[-1] not in file_tags[file_path]:
                    continue

                # Perform docker login if the registry is not already authenticated and credentials are provided
                repo_mod = (
                    dest_ms_url + "/registry/" + repository.split("registry/")[-1]
                )  # results in "<ms_url>/registry/<wl-name>"

                if client is None:
                    client = docker.from_env(timeout=600)
                if dest_ms_url not in docker.auth.load_config().get("auths", {}) and ms_usr and ms_psw:
                    log.info(" - docker login '%s'", dest_ms_url)
                    client.login(username=ms_usr, password=ms_psw, registry=f"https://{dest_ms_url}")
                log.info("Processing Docker image file: %s", file_path)
                with open(os.path.join(work_dir, file_path), "rb") as file:
                    log.info(
                        " - LOADED_IMAGE=$(docker image load -i %s | awk -F': ' '{print $2}')", file_path
                    )
                    images = client.images.load(file.read())
                loaded_image = images[0]
                if loaded_image.tag(repo_mod, tag=tag):
                    log.info(" - docker tag %s %s:%s", loaded_image.tags[0], repo_mod, tag)
                prev_status = ""
                log.info(" - docker push %s:%s", repo_mod, tag)
                for line in client.images.push(repo_mod, tag=tag, stream=True, decode=True):
                    if prev_status != line.get("status"):
                        log.debug(
                            "%s:%s - %s %s",
                            repo_mod,
                            tag,
                            line.get("status", ""),
                            line.get("progress", ""),
                        )
                        prev_status = line.get("status")
                try:
                    log.info(" - docker image rm %s:%s", repo_mod, tag)
                    client.images.remove(image=f"{repo_mod}:{tag}", force=True)
                except (docker.errors.APIError, docker.errors.DockerException) as e:
                    log.warning("Failed to remove image %s:%s - %s", repo_mod, tag, e)
                break
        else:
            log.info(
                "Image for target '%s' not found in discovered files for workload. Assuming image is already present on the registry.",
                repository.split("/", -1)[-1],
            )
    except (docker.errors.APIError, docker.errors.DockerException) as e:
        log.warning(
            "Make sure Docker is installed and running and you are logged in to the correct registry."
        )
        log.info("You can also try to push the image manually using following commands in the terminal:\n")
        for file_path in file_paths:
            log.info(" - LOADED_IMAGE=$(docker image load -i %s | awk -F': ' '{print $2}')", file_path)
            log.info(" - docker tag $LOADED_IMAGE %s:%s", repository, tag)
            log.info(" - docker push %s:%s", repository, tag)
            log.info(" - docker image rm %s:%s", repository, tag)

        raise RuntimeError(f"Error occurred while processing Docker images: {e}")
    finally:
        if client is not None:
            client.close()


def get_wl_def_from_path(work_dir, path, workload, log):
    """search through all subfolders for *.json files and check if the content is a workload definition file matching the workload defined"""
    required_keys = {"name", "description", "type", "disabled", "versions"}

    for sub_path in resolve_workload_file_paths(work_dir, path):
        for root, _, files in os.walk(sub_path):
            for file in files:
                if not file.endswith(".json"):
                    continue
                file_path = os.path.join(root, file)
                content = file_read(work_dir, file_path)
                if not isinstance(content, dict):
                    log.debug("Skipping file '%s' as it does not contain a valid JSON object", file_path)
                    continue  # not a valid JSON file
                if not all(key in content for key in required_keys):
                    log.debug(
                        "Skipping file '%s' as it does not contain all required workload definition keys",
                        file_path,
                    )
                    continue  # not a workload definition file

                search_workload = clean_wl_definition(workload)
                if all(
                    content.get(key) == value for key, value in search_workload.items() if key != "versions"
                ):
                    log.debug(
                        "Found workload definition file for workload '%s' at path '%s'",
                        workload["name"],
                        file_path,
                    )
                    return file_read(work_dir, file_path), file_path

    if all(key in workload for key in required_keys):
        log.debug("Using workload definition from input as it contains all required keys")
        return workload, "input"

    raise FileNotFoundError(
        f"No workload definition file found for workload '{workload.get('name', 'unknown')}'"
        f" of type '{workload.get('type', 'unknown')}' on search-path(s) '{resolve_workload_file_paths(work_dir, path)}'."
        " Please provide a valid workload definition file or check the provided path and filters."
    )


def get_version_file_paths(work_dir, path, wl_name, version, log):
    """Find files required to provision the workload"""

    # files can be dict or list
    search_iterator = (
        version.get("files", {}).values()
        if isinstance(version.get("files", {}), dict)
        else version.get("files", [])
    )
    search_files = search_iterator if version else []
    file_name = lambda f: f.get("originalName") or f.get("source", {}).split("/")[-1] or f.get("name")
    search_file_names = [file_name(s_file) for s_file in search_files]
    # some file-names can be docker-tags like ngingx:latest, those need to be checked in the manifest of the docker tar files
    search_file_docker_tags = [s_file for s_file in search_file_names if ":" in s_file]
    found_file_pathes = []
    for sub_path in resolve_workload_file_paths(work_dir, path):  # noqa: PLR1702
        # if sub_path is a file, check if it is the searched file and add to list, if it is a folder, search in all subfolders
        if os.path.isfile(sub_path) and os.path.basename(sub_path) in search_file_names:
            log.debug(
                "Found workload file '%s' for workload '%s' version '%s' at path '%s'",
                os.path.basename(sub_path),
                wl_name,
                version["name"],
                sub_path,
            )
            found_file_pathes.append(os.path.relpath(sub_path, work_dir))
        elif os.path.isdir(sub_path):
            for root, _, files in os.walk(sub_path):
                for file in files:
                    if file in search_file_names:
                        file_path = os.path.join(root, file)
                        log.debug(
                            "Found workload file '%s' for workload '%s' version '%s' at path '%s'",
                            file,
                            wl_name,
                            version["name"],
                            file_path,
                        )
                        found_file_pathes.append(os.path.relpath(file_path, work_dir))
                    elif file.endswith((".tar", ".tar.gz")) and search_file_docker_tags:
                        file_path = os.path.join(root, file)
                        repo_tags = get_repotags_from_docker_tar(work_dir, file_path, log)
                        for docker_tag in search_file_docker_tags:
                            if any(repo_tag.endswith(docker_tag) for repo_tag in repo_tags):
                                log.debug(
                                    "Found Docker image file '%s' containing tag '%s' for workload '%s' version '%s' at path '%s'",
                                    file,
                                    docker_tag,
                                    wl_name,
                                    version["name"],
                                    file_path,
                                )
                                found_file_pathes.append(os.path.relpath(file_path, work_dir))
                                break

    if len(search_file_names) < len(found_file_pathes):
        found_files_list = "\n - ".join(f for f in found_file_pathes)
        defined_files_list = "\n - ".join(f for f in search_file_names)
        raise ValueError(
            f"More files were found for workload '{wl_name}' version '{version.get('name', 'unknown')}'"
            " than defined in the workload definition. "
            f"Found files: \n - {found_files_list}.\n"
            f" Defined files: \n - {defined_files_list}.\n"
            " It is unclear which files belong to the workload, refine the path or define unique file-names"
        )
    search_file_names_required = [f for f in search_file_names if ":" not in f]  # exclude docker_tags
    if len(search_file_names_required) > len(found_file_pathes):
        missing_files_list = "\n - ".join(
            f for f in set(search_file_names_required) - {os.path.basename(f) for f in found_file_pathes}
        )
        raise FileNotFoundError(
            f"Not all workload files defined for workload '{wl_name}' version '{version['name']}' were found."
            f" Missing files: \n - {missing_files_list}"
        )

    return found_file_pathes


def ms_workloads_provision(ms_workloads, workloads, args, log=None):  # noqa: PLR0912, PLR0914, PLR0915
    if args.registry and args.legacy:
        raise ValueError(
            "Cannot set both 'registry' and 'legacy' flags. Please choose one of the registry types for provisioning the workload."
        )

    if isinstance(workloads, dict):
        workloads = [workloads]

    if len(workloads) == 0:
        log.error("No workloads found to provision with the provided filters")
        return 1

    perform_action = ask_for_confirmation(
        args,
        f"Are you sure you want to provision {len(workloads)} workload(s) to the management system {ms_workloads.ms.ms_url}?",
    )

    if isinstance(workloads, dict):
        workloads = [workloads]

    for search_workload in workloads:  # noqa: PLR1702
        workload, wl_def_file_path = get_wl_def_from_path(args.work_dir, args.provision, search_workload, log)
        wl_name = workload["name"]
        wl_type = workload["type"]

        # Validate if workload can be provisioned to MS
        existing_workload_on_ms = ms_workloads.get_workloads_dict(
            read_versions=False, compact_dict=False, filter_name=wl_name
        )
        existing_workload = next((iter for iter in existing_workload_on_ms if iter["name"] == wl_name), {})
        internal_docker_registry_expected = workload.get("internalDockerRegistry", False)
        if (args.legacy or args.registry) and workload["type"] in {"docker-compose", "docker"}:
            internal_docker_registry_expected = args.registry

        if existing_workload:
            if existing_workload.get("internalDockerRegistry", False) != internal_docker_registry_expected:
                raise AttributeError(
                    f"Workload '{wl_name}' already exists on the management system"
                    f" as an {'internal registry' if internal_docker_registry_expected else 'legacy'} workload."
                    f" To provision as {'legacy' if internal_docker_registry_expected else 'internal registry'} workload,"
                    " you would need to remove the workload first or change the workload name."
                )
            if existing_workload["type"] != wl_type:
                raise AttributeError(
                    f"Workload '{wl_name}' already exists on the management system with type '{existing_workload['type']}'."
                    f" The workload type must match to provision a workload with the same name."
                    " Please change the workload name or remove the existing workload first."
                )

        for version in workload["versions"]:
            wl_file_paths = get_version_file_paths(args.work_dir, args.provision, wl_name, version, log)
            log.info(
                "Files for %s workload '%s' with version '%s': \n    - %s",
                wl_type,
                wl_name,
                version["name"],
                "\n    - ".join([wl_def_file_path, *wl_file_paths]),
            )

            if not perform_action:
                log.info("Skipping provisioning of workload '%s' version '%s'", wl_name, version["name"])
                continue

            log.info(
                "Provisioning %s workload '%s' with version '%s' to MS '%s'...",
                wl_type,
                wl_name,
                version["name"],
                ms_workloads.ms.ms_url,
            )
            target_url = ms_workloads.ms.ms_url

            workload = modify_wl_def_registry_type(workload, args, log)

            if wl_type == "docker-compose":
                docker_compose_file = next(
                    iter(f_path for f_path in wl_file_paths if f_path.endswith((".yml", ".yaml"))), None
                )
                if not docker_compose_file:
                    raise FileNotFoundError(
                        f"Could not find docker compose file for workload '{wl_name}' with version '{version['name']}'"
                    )
                modify_docker_compose_file(
                    args.work_dir,
                    docker_compose_file,
                    target_url,
                    workload.get("internalDockerRegistry", False),
                )

            if workload.get("internalDockerRegistry", False) == True:
                images = []
                if wl_type == "docker-compose":
                    docker_compose_file = next(
                        (f for f in wl_file_paths if f.endswith((".yml", ".yaml"))), None
                    )
                    if docker_compose_file:
                        images = parse_docker_compose_for_images(args.work_dir, docker_compose_file)
                        log.debug(
                            "Parsed images from Docker Compose file '%s': \n  - %s",
                            docker_compose_file,
                            "\n  - ".join(f"{repo}:{tag}" for repo, tag in images),
                        )
                if wl_type == "docker":
                    for file in wl_file_paths:
                        if file.endswith((".tar", ".tar.gz")):
                            repo_tag = get_repotags_from_docker_tar(args.work_dir, file, log)[0]
                            if ":" in repo_tag:
                                repo, tag = repo_tag.rsplit(":", 1)
                            else:
                                repo = repo_tag
                                tag = "latest"
                            images.append((repo, tag))
                            wl_file_paths.append(f"{target_url}/registry/{repo}:{tag}")

                for repo, tag in images:
                    push_workload_to_docker_registry(
                        work_dir=args.work_dir,
                        file_paths=[path for path in wl_file_paths if path.endswith((".tar", ".tar.gz"))],
                        dest_ms_url=target_url,
                        repository=repo,
                        tag=tag,
                        ms_usr=ms_workloads.ms.usr,
                        ms_psw=ms_workloads.ms.psw,
                        log=log,
                    )
                # keep only yaml (docker-compose) file in list of files as the other files have been uploaded to registry
                wl_file_paths = [
                    file_path for file_path in wl_file_paths if not file_path.endswith((".tar", ".tar.gz"))
                ]

            if workload["type"] == "docker-compose" or workload.get("internalDockerRegistry") == True:
                api_version = 3
            else:
                api_version = 2

            wl_def_one_version = workload.copy()
            wl_def_one_version["versions"] = [version]

            wl_def = clean_wl_definition(wl_def_one_version)

            try:
                ms_workloads.provision_workload(
                    wl_def,
                    [os.path.join(args.work_dir, f) if "/registry/" not in f else f for f in wl_file_paths],
                    api_version,
                )
            except CheckStatusCodeError as ex_msg:
                if (
                    ex_msg.status_code == requests.codes.internal_server_error
                    and "Unable to upload file. Please check that archive is in correct format."
                    in ex_msg.response_text
                    and wl_def["type"] in {"docker", "docker-compose"}
                    and any(f.endswith(".tar.gz") for f in wl_file_paths)
                ):
                    log.warning(
                        "Upload to MS failed, probably due to invalid file-type, trying to change it to .tar"
                    )
                    renamed_files = []
                    for f in wl_file_paths:
                        if f.endswith(".tar.gz"):
                            os.rename(os.path.join(args.work_dir, f), os.path.join(args.work_dir, f[:-3]))
                            renamed_files.append(f)
                    wl_file_paths = [f[:-3] if f.endswith(".tar.gz") else f for f in wl_file_paths]
                    version_files = wl_def["versions"][0].get("files", [])
                    files_iterable = (
                        version_files.values() if isinstance(version_files, dict) else version_files
                    )
                    for file in files_iterable:
                        if "type" in file and file["type"] == ".gz":
                            if "originalName" in file:
                                file["originalName"] = (
                                    file["originalName"][:-3]
                                    if file["originalName"].endswith(".tar.gz")
                                    else file["originalName"]
                                )
                            file["type"] = ".tar"
                            file["containFileType"] = ""
                            file.pop("name", None)
                            file.pop("path", None)

                    try:
                        ms_workloads.provision_workload(
                            wl_def,
                            [
                                os.path.join(args.work_dir, f) if "/registry/" not in f else f
                                for f in wl_file_paths
                            ],
                            api_version,
                        )
                    finally:
                        # reverting change
                        for f in renamed_files:
                            os.rename(os.path.join(args.work_dir, f[:-3]), os.path.join(args.work_dir, f))
                    continue
                raise
    return 0
