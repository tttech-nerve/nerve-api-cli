# Nerve CLI Examples

This file provides practical, copy/paste-ready examples for the most common Nerve CLI tasks.
Examples are ordered from simple to advanced:

1. Simple examples with output and file-structure details
2. Common daily operations
3. Complete workflows

All commands use:

```bash
nerve-cli ...
```

If the `nerve-cli` command is not in your PATH, you can run it virtual environment with: 

```bash
poetry run nerve-cli ...
```

Or by activating the virtual environment first:

```bash
poetry shell
# if poetry-plugin-shell is not installed, use /path/to/venv/bin/activate
nerve-cli ...
```

## Prerequisites

Use one of the supported credential methods before running commands that access the Management System (MS):

- CLI flags: `--ms-url`, `--ms-user`, `--ms-password`
- `credentials.ini`
- Environment variables: `MS_URL`, `MS_USR`, `MS_PSW`

---

## Simple Examples

### 1. Verbosity And Work-Dir

Use case: run commands with more detailed logs and keep all generated/consumed files in one dedicated working
directory.

```bash
# INFO logs
nerve-cli -v ms-nodes list --output stdout:name

# DEBUG logs
nerve-cli -vv ms-nodes list --output stdout:name

# TRACE logs
nerve-cli -vvv ms-nodes list --output stdout:name

# Absolute work-dir example
nerve-cli --work-dir /tmp/nerve_demo ms-nodes list
```

Notes:

- `--work-dir /tmp/nerve_demo` is used to write files created by read operations from the MS (for example
  `nodes.json`, `workloads.json`).
- The same work-dir is also used to read local files for write operations to the MS (for example `--input
  workloads.json` during `ms-workloads provision`, or node/workload JSON files for deployment).

Expected file after the last command:

```text
/tmp/nerve_demo/
└── nodes.json
```

---

## Common Examples

### 2. List Nodes (Default Output: nodes.json)

Use case: create a local node inventory from the MS.

```bash
nerve-cli --work-dir ./demo ms-nodes list
```

What is created:

```text
./demo/
└── nodes.json
```

### 2a. List Nodes With Defined Output File

Use case: save node results to a custom file/path for later workflows.

```bash
nerve-cli --work-dir ./demo ms-nodes list --output exports/production_nodes.json
```

What is created:

```text
./demo/
└── exports/
    └── production_nodes.json
```

### 2a.1. List Nodes With Absolute Output Path

Use case: write node results to an absolute path, bypassing the work-dir setting. Useful for archiving to a central
location outside your project workspace.

```bash
nerve-cli --work-dir ./demo ms-nodes list --output /var/log/nerve/nodes_archive.json
```

What is created:

```text
/var/log/nerve/
└── nodes_archive.json
```

Notes:

- Absolute output paths (starting with `/` on Linux/macOS or drive letter on Windows) override `--work-dir`.
- Relative paths (e.g `./`) are always resolved relative to `--work-dir`.

### 2b. List Nodes With Output To stdout:name

Use case: quickly print node names (comma-separated) without creating a file.

```bash
nerve-cli ms-nodes list --output stdout:name
```

Example stdout output:

```text
edge-gateway-01,edge-gateway-02,edge-gateway-03
```

>[!NOTE]
> The output from logs is not included in the stdout output. Logs are > printed to stderr and can be redirected to a file if needed.

---

### 3. List Workloads (Default Output: workloads.json)

Use case: get a local list of workloads/versions from the MS to drive export/provision/deploy workflows.

```bash
nerve-cli --work-dir ./demo ms-workloads list
```

What is created:

```text
./demo/
└── workloads.json
```

---

### 4. Create Template (No MS Required)

Use case: generate a template you can edit locally before provisioning.

```bash
# Generates a Docker workload template locally
nerve-cli --work-dir ./demo template workload docker --output templates/docker_workload.json
```

What is created:

```text
./demo/
└── templates/
    └── docker_workload.json
```

Next step:

- Open `./demo/templates/docker_workload.json` and update values (name, version, image/files, ports, and so on).

---

### 5. Provision Workload From Template (Docker Registry)

Use case: provision a workload to the MS using a template and registry mode.

```bash
# 1) Generate a docker template that uses docker registry semantics
nerve-cli --work-dir ./demo template workload registry \
  --output templates_registry/registry_workload.json

# 2) Edit the template and set your workload metadata/image references
#    File to edit: ./demo/templates_registry/registry_workload.json

# 3) Provision to MS in registry mode
nerve-cli --work-dir ./demo --yes ms-workloads provision ./templates_registry \
  --input name:test_workload
```

> [!NOTE]
> The `--input name:test_workload` argument is used to select the workload template. The provision function will search for the template file in the `./templates_registry` folder relative to the work-dir. The search includes subfolders. It is possible to define multiple search paths (e.g. for workload *.tar files) by providing a comma-separated list of paths to the `--input` argument.

Typical local structure used in this flow:

```text
./demo/
└── templates_registry/
    └── registry_workload.json
```

---

## Complete Workflows

### 6. Complete Deploy Workflow (Filtered + --wait)

Use case: deploy one specific workload version only to a selected subset of nodes, wait for completion, then refresh
`nodes.json` to include updated workload state.

```bash
# 1) Build workload selection from MS
nerve-cli --work-dir ./demo ms-workloads list \
  --name nginx \
  --output deploy_workloads.json

# 2) Build node selection from MS (subset only)
nerve-cli --work-dir ./demo ms-nodes list \
  --name regex:edge-gateway-(01|02) \
  --online \
  --output deploy_nodes.json

# 3) Deploy and wait for completion
nerve-cli --work-dir ./demo --yes ms-workloads deploy deploy_nodes.json \
  --input deploy_workloads.json \
  --version-name v1 \
  --wait

# 4) Refresh node list after deployment to update workloads in nodes.json
nerve-cli --work-dir ./demo ms-nodes list \
  --name regex:edge-gateway-(01|02) \
  --online \
  --output deploy_nodes.json
```

What exists after this workflow:

```text
./demo/
├── deploy_nodes.json
├── deploy_workloads.json
```

---

### 7. Workload-DNA Workflow (Get Current, Apply To Other Node)

Use case: capture current workload-DNA from a source node and apply it to one or more target nodes.

```bash
# 1) Select source node
nerve-cli --work-dir ./demo ms-nodes list \
  --name edge-gateway-01 \
  --output source_node.json

# 2) Download current workload-DNA from source node
nerve-cli --work-dir ./demo ms-nodes workload-dna \
  --input source_node.json \
  --get-current dna_snapshots

# 3) Select target nodes
nerve-cli --work-dir ./demo ms-nodes list \
  --name regex:edge-gateway-(02|03) \
  --output target_nodes.json

# 4) Apply captured workload-DNA ZIP to targets
#    Replace SN0102030405 with the real serialNumber folder created in step 2.
nerve-cli --work-dir ./demo --yes ms-nodes workload-dna \
  --input target_nodes.json \
  --put-target dna_snapshots/SN0102030405/current_workload-dna.zip

# 5) Check status of workload-DNA deployment
nerve-cli --work-dir ./demo ms-nodes workload-dna \
  --input target_nodes.json \
  --status
  --output stdout:yaml
```

Created structure (example):

```text
./demo/
├── source_node.json
├── target_nodes.json
└── dna_snapshots/
    └── SN0102030405/
        └── current_workload-dna.zip
```

---

### 8. Node-DNA Workflow (Get Current, Edit, Put Target)

Use case: read current node-DNA, edit it locally, and apply it to target node(s).

```bash
# 1) Select source node
nerve-cli --work-dir ./demo ms-nodes list \
  --name edge-gateway-01 \
  --output node_dna_source.json

# 2) Download current node-DNA
nerve-cli --work-dir ./demo ms-nodes node-dna \
  --input node_dna_source.json \
  --get-current node_dna

# 3) Edit the generated YAML before applying
#    Example file: ./demo/node_dna/SN0102030405/current_node-dna.yaml

# 4) Select target nodes
nerve-cli --work-dir ./demo ms-nodes list \
  --name regex:edge-gateway-(02|03) \
  --output node_dna_targets.json

# 5) Apply edited node-DNA file to targets
nerve-cli --work-dir ./demo --yes ms-nodes node-dna \
  --input node_dna_targets.json \
  --put-target node_dna/SN0102030405/current_node-dna.yaml
```

Created structure (example):

```text
./demo/
├── node_dna_source.json
├── node_dna_targets.json
└── node_dna/
    └── SN0102030405/
        └── current_node-dna.yaml
```

---

### 9. Workload Export, Change, And Provision Again

Use case: export the last two workload versions, modify one version (new `version-name` and updated `.tar` file), then
upload it again with `provision`.

```bash
# 1) Export the last two versions
nerve-cli -v --work-dir ./demo/ ms-workloads export export_workloads --version-list-filter=-2: --input name:nginx
```

Expected result:

- The last two versions per selected workload are exported.
- The export creates a folder structure under `./demo/export_-_workloads/` with workload and version subfolders.

```text
./demo/
└── export_-_workloads/
    └── nginx/
        ├── v1/
        │   ├── wl_def.json
        │   └── nginx_v1.tar
        └── v2/
            ├── wl_def.json
            └── nginx_v2.tar
```

```bash
# 2) Change the exported workload locally
#    - Open wl_def.json in the version folder you want to reuse
#    - Update versions[0].name to a new version name (for example v2-hotfix)
#    - Update the originalName in versions[0].files[...].name to a new .tar file name
#    - Replace/update the referenced .tar file

# 3) Upload again with provision from specific version folder
nerve-cli --work-dir ./demo/ --yes ms-workloads provision export-workloads/nginx/v2 \
  --input name:nginx
```

Lightweight export suggestion for registry workloads:

```bash
# Exports only workload definitions (and docker-compose file if applicable)
# No workload binary files are downloaded.
nerve-cli --work-dir ./demo/ ms-workloads export export-workloads-template \
  --template \
  --version-list-filter=-2:
```

When to use `--template`:

- You want a quick metadata export for review/change tracking.
- You work with registry-based workloads and do not need to download workload files.
  - When provisioning registry workloads without workload files, it is expected that the registry has the referenced images available for download.
  - A registry workload provisioning without the referenced images beeing present will fail when checking for deployable state.

## Additional Tips

- Use `--output stdout:json` or `--output stdout:yaml` for quick inspection without writing files.
- Use regex filters for subsets, for example `--name regex:edge-gateway-(01|02)`.
- Use `--dry-run` to preview mutating operations and `--yes` to skip interactive confirmations. 
- Arguments like `--dry-run` and `--yes` must be placed before the subcommand (for example `ms-nodes`, `ms-workloads`, `template`, and so on).
- Use verbosity flags `-v` to increase log-level output. The `INFO` log level will show which files had been written. 
