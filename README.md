<p align="center" style='font-size: 12px; font-family: "Monaco";'>
    <img src="./img/logo-nerve-black.svg" alt="Nerve"/><b>&nbsp;API CLI</b><br><br>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg"/></a>
    <a href="https://docs.python.org/3/"><img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg"/></a>
    <a href="https://docs.nerve.cloud"><img src="https://img.shields.io/badge/nerve-2.9%20%7C%202.10%20%7C%203.0%20%7C%203.1.1-blue.svg"/></a>
</p>

The *Nerve API CLI* provides a command line interface to the REST API of a [Nerve Management System](https://docs.nerve.cloud). It is essentially a command line wrapper for some parts of the [*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python) and can be used to integrate *Nerve* related workflows into a build pipeline and automate common tasks such as workload creation and deployment. Since the CLI does only cover a subset of functions provided by the *[*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python.git)* please refer to the library directly if additional flexibility or functionality is needed.

## Installation

The scripts have been developed and tested with Python 3.11+, and it is recommended to run them with Python 3.11 or later. 

> Note that the instructions below are for Linux operating systems. For information on how to create a virtual environment on Windows, please refer to [the official Python documentation](https://python.land/virtual-environments/virtualenv#How_to_create_a_Python_venv).


The library is developed with poetry. 
Install poetry
``` sh
curl -sSL https://install.python-poetry.org | python3 -
```

Install the dependencies: `poetry install`

Check if everything works as intended: `poetry run nerve-cli --help`


Optional: Activate the environment and use the command-line entry-point
```
poetry self add poetry-plugin-shell  // adds a shell option to poetry, only needs to be exectued once.
poetry shell  // deactivate the environment with Ctrl+D

nerve-cli --help
```

## License

The source code is released under MIT license (see the [LICENSE](./LICENSE) file).

# Command-line use and use as a library

The repository is a wrapper to the *[*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python.git)*.
The *nerve_cli* contains the functions for executing interactively from the command line.
The [*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python.git) contains the Python module which encapsulates the API.
The individual Python files are structured along the objects they work on. To accomplish a specific task using the API functions, looking into the implementation of the corresponding command in the commands directory may be a good starting point.


## Command-line use

Run `nerve-cli` with arguments. See `--help` for usage details or refer to the help output below:

```
usage: nerve-cli [-h] [--yes] [--dry-run] [--ms-url URL] [--ms-user USERNAME] [--ms-password PASSWORD] [--work-dir PATH]
                 [-v] [--store-credentials]
                 {cli,template,ms-workloads,ms-nodes,ms-labels,local-node} ...

Nerve API CLI for managing devices, workloads, labels, and remote connections.

positional arguments:
  {cli,template,ms-workloads,ms-nodes,ms-labels,local-node}
                        Available subcommands:
    cli                 Start interactive CLI mode.
    template            Generate templates for workload definitions or remote connections.
    ms-workloads        Manage workloads on the management system (list, export, provision, delete, deploy).
    ms-nodes            Manage nodes on the management system (list, reboot, workload state, DNA, remote connections), with
                        filtering support.
    ms-labels           Manage labels on the management system.
    local-node          Manage nodes using local API.

options:
  -h, --help            show this help message and exit
  --yes                 Auto-confirm all prompts (skip interactive confirmations)
  --dry-run             Preview changes without applying them (overrides --yes)
  --work-dir PATH       PATH TO working directory for temporary files (default: current directory)
  -v, --verbose         Increase verbosity: -v=INFO, -vv=DEBUG, -vvv=TRACE. Defaults: WARNING for command mode,
                        INFO for interactive cli mode.
  --store-credentials   Save credentials to credentials.ini file (security warning: stores plaintext password)

Management System Settings:
  --ms-url URL          Management System URL (e.g., example-ms.nerve.cloud). Priority: (1) command-line arg, (2) env-var MS_URL (3)
                        credentials.ini (only if it contains exactly one section)
  --ms-user USERNAME    Management System login username. Priority: (1) command-line arg, (2) credentials.ini, (3) env-var MS_USR
  --ms-password PASSWORD
                        Management System login password. Priority: (1) command-line arg, (2) credentials.ini, (3) env-var MS_PSW
```

The credentials may be provided in three different ways (sorted by priority):

- via command line arguments: `poetry run nerve-cli --ms-url my-management-system.nerve.cloud --ms-user myusername --ms-password mypassword`
- via `credentials.ini` file.
- via environment variables (set the `MS_URL`, `MS_USR`, and `MS_PSW` environment variables). Check the *set_login_environment_vars.sh* script to understand the naming of the variables.

A credentials file must have the following form:
```ini
[my-management-system.nerve.cloud]
username = myusername
password = mypassword
```

The file may also contain multiple sections. The section name, defines the management system URL (without https://).
When working with multiple Management Systems the use of `credentials.ini` file is convenient but note that the password is stored in plain text, which might create a security risk. The CLI argument `--ms-url` should be defined to work with the correct
management system, but the passwords will be retrieved from the `credentials.ini` without the need to define them in env-vars or the command-line arguments. To add new entries to the credentials file the `--store-credentials` flag can be used. This will add the credentials provided via command-line arguments to the `credentials.ini` file. If the file does not exist, it will be created.

### Example Usage

Run `poetry run nerve-cli --help` to get detailed information about all available commands.

When the credentials are defined, any command can be run without performing a login upfront. The [*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python.git) will automatically detect if a new login is required and use the 
provided credentials if needed.

When a login is triggered can be noticed in the command line output when debug mode is activated
`poetry run nerve-cli -vv`.


For example it is possible to perform operations on the Management System such as listing all the Docker workloads that are available on the Management System:

```bash
poetry run nerve-cli ms-workloads list --type docker --output workloads.json
```
This will write the result into the JSON file *workloads.json*. Command mode defaults to log level WARNING.
Use `-v` for INFO, `-vv` for DEBUG, and `-vvv` for TRACE. Interactive `cli` mode defaults to INFO. For
more details about the command, check the help with `poetry run nerve-cli ms-workloads -h` and the
action-specific help with `poetry run nerve-cli ms-workloads list -h`.

Another use case might be to get a list of all nodes where a specific workload version is currently deployed:
``` bash
poetry run nerve-cli ms-nodes list --name nginx --workload-version-name v1 --output nodes.json
```
This lists all nodes where the workload with the name "nginx" is deployed in version "v1" and saves the output as JSON into the *nodes.json*.

To change the state of workloads on selected nodes, use the dedicated action with a positional `STATE` argument:

```bash
poetry run nerve-cli ms-nodes set-workload-state START --input nodes.json --workload-name nginx
```

To inspect only DNA-related options for workload DNA actions:

```bash
poetry run nerve-cli ms-nodes workload-dna -h
```

To add or delete labels, provide the label source as a positional `SOURCE` argument:

```bash
poetry run nerve-cli ms-labels add pairs:env:prod,site:vienna
poetry run nerve-cli ms-labels delete labels.json
```

The scripts also provide a workflow to create a new workload. Start by generating a template for the desired workload type:

```bash
poetry run nerve-cli template workload docker --output wl_def_docker.json
```

Open the *wl_def_docker.json* file with a text editor, adjust it to your needs, and save it.
The new workload can now be provisioned on the Management System with the following command.

```bash
poetry run nerve-cli ms-workloads provision workload_folder --input wl_def_docker.json
```

Version-level filters are available for `ms-workloads provision`, `ms-workloads export`,
`ms-workloads delete`, and `ms-workloads deploy`. This is useful if the input contains multiple versions
and only a subset should be processed.

```bash
poetry run nerve-cli ms-workloads export exported_workloads --input workloads.json --version-name v1
```

### Filter Pattern Syntax

Several filter arguments (e.g., `--name`, `--serial-number`, `--version`, `--workload-name`, `--remote-connection-name`, `--filter-name`) support two matching modes:

| Mode | Prefix | Example |
|---|---|---|
| Exact string match | *(none)* | `--name mynode` |
| Regular expression | `regex:` or `regexp:` | `--name regex:node_[0-9]+` |

Both `regex:` and `regexp:` are equivalent and trigger `re.search()` matching against the full field value.

```bash
# Exact match
poetry run nerve-cli ms-nodes list --name mynode

# Regex match (matches node_1, node_42, …)
poetry run nerve-cli ms-nodes list --name regex:node_[0-9]+
poetry run nerve-cli ms-nodes list --name regexp:node_[0-9]+

# Regex on workload name
poetry run nerve-cli ms-nodes list --workload-name regex:nginx.*
```

### Interactive shell command restrictions

When running `poetry run nerve-cli cli`, shell execution is restricted to an internal allowlist.
This applies to both `shell <command>` and `!<command>` syntax in interactive mode.

- Allowed commands: `cat`, `cd`, `echo`, `ll`, `ls`, `nano`, `notepad`, `pwd`, `vi`, `vim`
- `ll` is treated as an alias for `ls`
- Windows aliases: `type` maps to `cat`, `dir` maps to `ls`, and `vi`/`nano` run as `notepad`
- Non-allowlisted commands are rejected with an explicit error message

This restriction prevents command injection vectors that depend on unrestricted shell execution.

## Use the library directly

To use the [*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python.git) examples defined in the CLI tool can be used as a starting point. The [*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python.git) is structured in several sections allowing to control the complete management system using API calls. The general_utils.py contains the main handles for the management system and the local UI interface of the nodes. The other lib-files extend the handles with additional functions. 
All API functions make extensive use of exceptions to inform the user about unforeseen problems in the call. Make sure to expect those.