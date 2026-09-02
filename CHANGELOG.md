# Changelog

# Release 2.0.0
- Adding label management for ms-nodes commands:
  - `ms-nodes labels add/delete/edit` to manage one or more labels of a node, multiple actions can be performed in one command
  - `ms-nodes labels export/import` to export/import all labels of a node to/from a file
- Adding compose-restrictions management for ms-nodes commands:
  - `ms-nodes compose-restrictions get <path>` to read the `compose-restrictions.json` file from nodes and save it to PATH
  - `ms-nodes compose-restrictions version <path>` to read the active `compose-restrictions.json` version from nodes and save it to PATH
  - `ms-nodes compose-restrictions update <file>` to update the `compose-restrictions.json` file on nodes from FILE, optionally using
    `--base-version` or `--force` to control which version the update is based on
- Adding access token management with the new `ms-access-token` subcommand:
  - `ms-access-token list/create/delete/unlock-brute-force/permissions` actions, each showing only its
    relevant arguments in `-h` help output, following the same `<command> <action>` pattern as `ms-labels`
    and `ms-nodes`.
  - Access tokens can be used instead of username/password via the `--ms-token` argument, the `MS_ACCESS_TOKEN`
    environment variable, or the `access_token` key in `credentials.ini`, giving more granular control over the
    permissions available to automation and CI use-cases.
- Refactored nerve-cli structure to a more modular design, improving maintainability and scalability.
  - Using `-` separators for all subcommands and arguments instead of `_` to align with common CLI conventions.
  - Main sections for one-shot commands: `template`, `ms-workloads`, `ms-nodes`, `ms-labels`, `local-node`. Each section has its own subcommands and arguments, allowing for better organization and easier navigation.
  - `cli` section starts an interactive shell for executing commands in a more user-friendly manner.
  - Changed default log level to `WARNING` to reduce verbosity. Users can still set the log level to `INFO` or `DEBUG` using the `-v`or `-vv` flags. The `cli` section will start in `INFO` log level by default.
- Hardened interactive CLI shell execution with a strict command allowlist for `shell` and `!` commands.
- **Known Limitiation**: 
  - Added an experimental feature to manage remote tunnel and screen connections for nodes from INPUT. This feature is still under development and may have limited functionality. Use with caution.
  - Created templates for remote connections and workloads do not provide a schema. The templates section will be enhanced in future releases to include schema file.

# Release 1.3.0
- Improved performance of get workload list by applying filters on request

# Release 1.2.0
- Fixed issue with defining paths to files (absolute path vs relative path)
- Updated library versions, code cleanup, fixed StatusCode error reporing
- Removing missleading shorts of arguments
- Adding 'paste' mechanism to allow a copy-paste from one MS to another or to change the workload type from legacy to docker-registry
- Adding backup and restore functions for docker-volumes over local-ui connection to a node.
    > [!Tip] Usage of backup and restore functions:
        Backup all names volumes of a node connected via mgmt port: 
        `nerve-cli docker_volumes --localui_password <password> --backup`\        
        The volume backup data is stored in the _`<workdir>/volumes_backup/<NodeSerial>/<volumes>.zip`_\
        To restore the volumes on a node, use the argument `--restore`\
        If the default admin account is deactivated, the MS credentials can be used by providing the MS URL (using stored credentials) or 
        the MS password and MS user explicitly.\
        Example: `nerve-cli --ms_url <ms-url.nerve.cloud> docker_volumes --backup`
- Adding non 0 exit codes in case of an error

# Release 1.1.0
- Fixed download/copy function of workloads
- Removed sessions file as the nerve-lib will logout automatically from MS. Session key cannot be reused
- Added cli for Service-OS-DNA functions
- Fixed DNA reapply_target call
- Improved error-reporting

# Release 1.0.0
- Initial version
