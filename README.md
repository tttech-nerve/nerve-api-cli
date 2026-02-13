<p align="center" style='font-size: 12px; font-family: "Monaco";'>
    <img src="./img/logo-nerve-black.svg" alt="Nerve"/><b>&nbsp;API CLI</b><br><br>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg"/></a>
    <a href="https://docs.python.org/3/"><img src="https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg"/></a>
    <a href="https://docs.nerve.cloud"><img src="https://img.shields.io/badge/nerve-2.9%20%7C%202.10%20%7C%203.0-blue.svg"/></a>
</p>

The *Nerve API CLI* provides a command line interface to the REST API of a [Nerve Management System](https://docs.nerve.cloud). It is essentially a command line wrapper for some parts of the [*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python) and can be used to integrate *Nerve* related workflows into a build pipeline and automate common tasks such as workload creation and deployment. Since the CLI does only cover a subset of functions provided by the *[*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python.git)* please refer to the library directly if additional flexibility or functionality is needed.

## Installation

The scripts have been developed and tested with Python 3.10+, and it is recommended to run them with Python 3.10 or later. 

> Note that the instructions below are for Linux operating systems. For information on how to create a virtual environment on Windows, please refer to [the official Python documentation](https://python.land/virtual-environments/virtualenv#How_to_create_a_Python_venv).


The library is developed with poetry. 
Install poetry
``` sh
curl -sSL https://install.python-poetry.org | python3 -
```

Install the dependencies: `poetry install`

Check if everything works as intended: `poetry run python -m nerve_cli --help`


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

Start the function running `nerve.py` with arguments. See `--help` for usage details or refer to the help output below:

```
usage: nerve-cli [-h] [--ms_url <MS_url>] [--ms_user <MS_username>] [--ms_password <MS_password>] [--work_dir <directory>] [-l {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
             {cli,workload_create,ms_workloads,nodes_list,nodes_reboot,nodes_workloads_state,nodes_remote_connections,labels,logout} ...

Nerve API CLI for deploying applications to devices.

positional arguments:
  {cli,workload_create,ms_workloads,nodes_list,nodes_reboot,nodes_workloads_state,nodes_remote_connections,labels,logout}
                        Available sub-commands:
    cli                 Start the interactive CLI
    workload_create     Create a new workload on the management system. An option allows to create a template.
    ms_workloads        Create a workloads json file based on filter options, and perform actions on these workloads like deploy or delete.
    nodes_list          Create a nodes json file based on different filter options.
    nodes_reboot        Reboot nodes
    nodes_workloads_state
                        Change the state of all workloads listed in the nodes file
    nodes_remote_connections
                        Manage remote tunnels from nodes
    labels              Manage labels on the management system
    logout              Logout from the management system

optional arguments:
  -h, --help            show this help message and exit
  --work_dir <directory>
                        Directory to store temporary files (defaults to work_dir)
  -l {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --log_level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Set the log level (default: INFO)

Management System Settings:
  --ms_url <MS_url>     Url of the Nerve MS. If a credentials.ini file exists with only one section, the MS will be set to this (default to env-var MS_URL)
  --ms_user <MS_username>
                        Login user for Nerve MS (user is read from credentials.ini file or defaults to env-var MS_USR)
  --ms_password <MS_password>
                        Login password for Nerve MS (password is read from credentials.ini file or defaults to env-var MS_PSW)
```

The credentials may be provided in three different ways:

- via command line arguments: `poetry run nerve-cli --ms_url my-management-system.nerve.cloud --ms_user myusername --ms_password mypassword`
- via environment variables (set the `MS_URL`, `MS_USR`, and `MS_PSW` environment variables). Check the *set_login_environment_vars.sh* script to understand the naming of the variables.
- via `credentials.ini` file.

A credentials file must have the following form:
```ini
[my-management-system.nerve.cloud]
username = myusername
password = mypassword
```
The file may also contain multiple sections. The section name, defines the management system URL (without https://).
When working with multiple Management Systems the use of `credentials.ini` file is recommended. The CLI app argument --ms_url must be defined to work with the correct
management system, but the passwords will be retrieved from the `credentials.ini` without the need to define them in env-vars or the command-line arguments. 

### Example Usage

Run `poetry run nerve-cli --help` to get detailed information about all available commands.

When the credentials are defined, any command can be run without performing a login upfront. The [*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python.git) will automatically detect if a new login is required and use the 
provided credentials if needed.

When a login is triggered can be notices in the command line output when the debug mode is activated `poetry run nerve-cli --log_level DEBUG`. 


For example it is possible to perform operations on the Management System such as listing all the Docker workloads that are available on the Management System:

```bash
poetry run nerve-cli ms_workloads --list --type docker --file workloads.json
```
This will write the result into the JSON file *workloads.json*. The output on the command line is creating logs in different log-levels. Per default log-level INFO is defined which will show human-readable results of the commands. For more details about the command, check the help with `poetry run nerve_cli ms_workloads --help`.

Another use case might be to get a list of all nodes where a specific workload version is currently deployed:
``` bash
poetry run nerve-cli nodes_list -wn nginx -wvn v1 --file nodes.json
```
This lists all nodes where the workload with the name "nginx" is deployed in version "v1" and saves the output as JSON into the *nodes.json*.

The scripts also provide a workflow to create a new workload. Define the workload via a JSON file. To make it easier to create such a file, a template can be created for different workload types:

```bash
poetry run nerve-cli workload_create --template docker --file wl_def_docker.json
```

Open the *work_dir/wl_def_docker.json* file with a text editor and adjust it to your needs to represent the new workload to be created and save it.
The new workload can now be created on the Management System with the following command.

```bash
poetry run nerve-cli workload_create --create --file wl_def_docker.json --path ../../images/nginx.tar.gz
```

## Use the library directly

To use the [*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python.git) examples defined in the CLI tool can be used as a starting point. The [*nerve_lib*](https://github.com/tttech-nerve/nerve-api-python.git) is structured in several sections allowing to control the complete management system using API calls. The general_utils.py contains the main handles for the management system and the local UI interface of the nodes. The other lib-files extend the handles with additional functions. 
All API functions make extensive use of exceptions to inform the user about unforeseen problems in the call. Make sure to expect those.
