import json as _json
import os
import re
import shlex
from time import time
from typing import Dict, List, Optional, Union, Any, Callable, Tuple

from utils import cmd_to_array, log, run_command

from utils.exceptions import *  # noqa  # isort:skip


os.environ["TF_IN_AUTOMATION"] = "1"
# os.environ['TF_LOG'] = 'trace'

log.show_file(False)
log.set_level("info")

VERSION_REGEX = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")

TERRAFORM_ARGS = {
    "color": "-no-color",
    "lock": "-lock=",
    "lock_timeout": "-lock-timeout=",
    "input": "-input=",
    "upgrade": "-upgrade",
    "from_module": "-from-module=",
    "reconfigure": "-reconfigure",
    "migrate_state": "-migrate-state",
    "force_copy": "-force-copy",
    "backend": "-backend=",
    "backend_config": "-backend-config=",
    "get": "-get=",
    "get_plugins": "-get-plugins=",
    "plugin_dir": "-plugin-dir=",
    "lockfile": "-lockfile=",
    "readonly": "-lockfile=readonly",
    "chdir": "-chdir=",
    "update": "-update",
    "destroy": "-destroy",
    "out": "-out=",
    "refresh_only": "-refresh-only",
    "refresh": "-refresh=",
    "replace": "-replace=",
    "target": "-target=",
    "var": "-var=",
    "var_file": "-var-file=",
    "compact_warnings": "-compact-warnings",
    "json": "-json",
    "parallelism": "-parallelism=",
    "auto_approve": "-auto-approve",
    "state": "-state=",
    "state_out": "-state-out=",
    "backup": "-backup=",
    "list": "-list=",
    "diff": "-diff",
    "write": "-write=",
    "check": "-check",
    "recursive": "-recursive",
    "raw": "-raw"
}


class Terraform:
    """
    A Python wrapper for Terraform CLI operations.

    This class provides methods for executing Terraform commands including
    init, plan, apply, show, and destroy. It handles argument formatting,
    command execution, and output parsing.

    Attributes:
        _workspace (str): The Terraform workspace name
        chdir (str): The directory where Terraform commands will be executed
        _lock (bool): Whether to use state locking
        _lock_timeout (int): How long to wait for state lock
        _input (bool): Whether to ask for input interactively
        _paralellism (int): Number of parallel operations
        _color (bool): Whether to use color in output
        _var_file (str): Path to variable definition file
        _version (dict): Terraform version information
        _planfile (str): Default plan file name

    Example:
        ```python
        # Initialize Terraform wrapper
        tf = Terraform(chdir="./terraform_project")

        # Run init and plan
        tf.init(upgrade=True)
        tf.plan(vars={"environment": "production"})

        # Apply the changes
        result = tf.apply(auto_approve=True)
        ```
    """

    def __init__(
        self,
        workspace: str = "default",
        chdir: Optional[str] = None,
        lock=True,
        lock_timeout=0,
        input=False,
        parallelism=10,
        color=True,
        var_file: str = None,
    ):
        log.set_env(workspace)
        self._workspace = workspace
        self.chdir = chdir
        self._lock = lock
        self._lock_timeout = lock_timeout
        self._input = input
        self._paralellism = parallelism
        self._color = color
        self._var_file = var_file
        self._version = self.version()
        self._planfile = "plan.tfplan"

    def version(self) -> Dict[str, Any]:
        """
    Retrieve Terraform version information.

    Executes 'terraform version -json' and parses the output to extract
    version details including major, minor, and patch numbers.

    Returns:
        Dict[str, Any]: A dictionary containing version information with keys:
            - version: Dict with major, minor, patch version numbers
            - version_str: Full version string
            - latest: Boolean indicating if this is the latest version
            - platform: Platform information

    Raises:
        TerraformVersionError: If unable to retrieve version information
    """
        result = run_command(cmd_to_array(
            "terraform version -json"), show_output=False)
        if result.success is False:
            raise TerraformVersionError(
                "Failed to retrieve terrform version", "version", result.stderr
            )
        version = _json.loads(result.stdout)
        version_str = version["terraform_version"]

        version_dict = VERSION_REGEX.match(version_str)
        if version_dict:
            version_dict = version_dict.groupdict()
            for key in version_dict.keys():
                version_dict[key] = int(version_dict[key])
        else:
            version_dict = dict(major=0, minor=0, patch=0)
        result = {
            "version": version_dict,
            "version_str": version_str,
            "latest": version["terraform_outdated"] == False,
            "platform": version["platform"],
        }
        self._version = result
        return result

    def color(self, enable: bool = True):
        """
        Set color output option.

        Args:
            enable (bool): Whether to enable color output. Defaults to True.
        """
        self._color = enable

    def lock(self, enable: bool = True):
        """
        Set state locking option.

        Args:
            enable (bool): Whether to enable state locking. Defaults to True.
        """
        self._lock = enable

    def input(self, enable: bool = False):
        """
        Set interactive input option.

        Args:
            enable (bool): Whether to enable interactive input. Defaults to False.
        """
        self._input = enable

    def lock_timeout(self, timeout: int = 0):
        """
        Set state lock timeout.

        Args:
            timeout (int): Lock timeout in seconds. Defaults to 0.
        """
        self._lock_timeout = timeout

    @staticmethod
    def _build_arg(arg: str, value) -> str:
        """
    Build a formatted command-line argument string for Terraform.

    Args:
        arg (str): Argument name as defined in TERRAFORM_ARGS
        value: Value for the argument, can be string, bool, or None

    Returns:
        str: Formatted argument string or empty string if the argument should be omitted
    """
        res = TERRAFORM_ARGS[arg]
        if res[-1] == "=" and value is not None:
            if isinstance(value, bool):
                res += "true" if value else "false"
            elif isinstance(value, str) and len(value) == 0:
                return ""
            elif value is not None and len(str(value)) > 0:
                res += str(value)

        elif isinstance(value, bool):
            return res if value else ""
        else:
            return ""
        return res

    def _default_args(
        self,
        color: bool = None,
        lock: bool = None,
        lock_timeout: int = None,
        input: bool = None,
    ) -> list:
        """Format default args

        Args:
            color (bool, optional): Enables terraform color output. Defaults to None.
            lock (bool, optional): Enables terrafom state lock. Defaults to None.
            lock_timeout (int, optional): Timeout of lock state. Defaults to None.
            input (bool, optional): Enables user input for commands that requires it. Defaults to None.

        Returns:
            list: List of cli argumments
        """

        args = []

        if color is not None:
            args.append(Terraform._build_arg("color", color))
        elif self._color is False:
            args.append(TERRAFORM_ARGS["color"])
        if lock is not None and lock is False:
            args.append(Terraform._build_arg("lock", lock))
        elif self.lock is False:
            args.append(Terraform._build_arg("lock", self._lock))

        if lock_timeout is not None and lock_timeout > 0:
            args.append(Terraform._build_arg("lock_timeout", lock_timeout))
        elif self._lock_timeout > 0:
            args.append(Terraform._build_arg(
                "lock_timeout", self._lock_timeout))

        if input is not None:
            args.append(Terraform._build_arg("input", input))
        elif self._input is False:
            args.append(Terraform._build_arg("input", self._input))
        return args

    def _global_args(self, chdir: str = None):
        """Global terraform args formatter

        Args:
            chdir (str, optional): Workdir for terraform command to run. Defaults to None.

        Returns:
            list[str]: List of formatted cli args
        """
        args = []

        if chdir is not None:
            args.append(Terraform._build_arg("chdir", chdir))
        elif self.chdir is not None and self.chdir != ".":
            args.append(Terraform._build_arg("chdir", self.chdir))
        return args

    @staticmethod
    def cmd(
        command: list,
        title: Optional[str] = None,
        chdir: Optional[str] = None,
        show_output: bool = True,
        callback: Optional[Callable[[
            Optional[str], Optional[str]], Any]] = None,
        line_callback: Optional[Callable[[
            Optional[str], Optional[str]], Any]] = None,
    ):
        """Run CLI Terraform command

    This method executes the specified Terraform command with the given arguments
    and returns the result. It supports callbacks for processing command output.

    Args:
        command (list): List of arguments for terraform command
        title (str, optional): Title of the command to run. Defaults to None.
        chdir (str, optional): Working directory to run the command in. Defaults to None.
        show_output (bool, optional): Show command output. Defaults to True.
        callback (Callable(str,str)->Any, optional): Function to handle command output (stdout,stderr). Defaults to None.
        line_callback (Callable(str,str)->Any, optional): Function to handle per line command output. Defaults to None.

    Returns:
        CommandResult: Result of the command with attributes:
            - success: Boolean indicating if the command succeeded
            - stdout: Standard output from the command
            - stderr: Standard error from the command
            - callback_output: Output from the callback function if provided
            - duration: Code runtime duration

    Example:
        ```python
        def process_output(stdout, stderr):
            return {"processed": stdout}

        result = tf.cmd(["show"], callback=process_output)
        ```
    """
        cmd = ["terraform"]
        cmd.extend(command)
        return run_command(
            cmd,
            title=title,
            cwd=chdir,
            show_output=show_output,
            callback=callback,
            line_callback=line_callback,
        )

    def init(
        self,
        color: Optional[bool] = None,
        lock: Optional[bool] = None,
        lock_timeout: Optional[int] = None,
        input: Optional[bool] = None,
        upgrade: bool = False,
        reconfigure: bool = False,
        migrate_state: bool = False,
        force_copy: bool = False,
        backend: bool = True,
        backend_config: Optional[str] = None,
        get: bool = True,
        get_plugins: bool = True,
        plugin_dir: Optional[str] = None,
        readonly: bool = False,
        chdir: Optional[str] = None,
    ):
        """
        Initialize a working directory containing Terraform configuration files.

        Args:
            color (bool): Enable color output
            lock (bool): Use state locking
            lock_timeout (int): State lock timeout
            input (bool): Enable interactive input
            upgrade (bool): Upgrade modules and plugins
            reconfigure (bool): Reconfigure backend
            migrate_state (bool): Migrate state to new backend
            force_copy (bool): Force copy from previous backend
            backend (bool): Configure backend
            backend_config (str): Backend configuration
            get (bool): Download modules
            get_plugins (bool): Download plugins
            plugin_dir (str): Plugin directory
            readonly (bool): Readonly mode
            chdir (str): Directory to change to before running command

        Returns:
            bool: Success status

        Raises:
            TerraformInitError: If initialization fails
        """
        cmd = ["init"]

        if readonly:
            cmd.append(Terraform._build_arg("readonly", readonly))

        cmd.extend(
            self._default_args(
                color=color, lock=lock, lock_timeout=lock_timeout, input=input
            )
        )

        cmd.append(Terraform._build_arg("upgrade", upgrade))
        cmd.append(Terraform._build_arg("reconfigure", reconfigure))
        cmd.append(Terraform._build_arg("migrate_state", migrate_state))
        cmd.append(Terraform._build_arg("force_copy", force_copy))
        cmd.append(Terraform._build_arg("backend_config", backend_config))
        cmd.append(Terraform._build_arg("plugin_dir", plugin_dir))
        # cmd.append(Terraform._build_arg("lockfile", lockfile))

        if not backend:
            cmd.append(Terraform._build_arg("backend", backend))
        if not get:
            cmd.append(Terraform._build_arg("get", get))
        if not get_plugins:
            cmd.append(Terraform._build_arg("get_plugins", get_plugins))
        if not chdir:
            chdir = self.chdir
        result = Terraform.cmd(cmd, title="Terraform init", chdir=chdir)
        if result.success:
            log.success(
                f"Terraform init completed in: {result.duration} seconds")
        else:
            raise TerraformInitError(
                "Failed to initialize terraform project",
                "init",
                result.stderr,
                result.duration,
            )
        return result.success

    def get(self, update: bool = None, color: bool = None):
        """Terraform get command

        Args:
            update (bool, optional): Update state file. Defaults to None.
            color (bool, optional): Show color in outputs. Defaults to None.

        Raises:
            TerraformGetError: Terraform Get Error Exception

        Returns:
            bool: Command was successful
        """
        cmd = ["get"]
        cmd.append(Terraform._build_arg("update", update))
        cmd.append(Terraform._build_arg("color", color))

        result = Terraform.cmd(cmd, title="Terraform get", chdir=self.chdir)
        if result.success:
            log.success(
                f"Terraform get completed in: {result.duration} seconds")
        else:
            raise TerraformGetError(
                "Failed to run terraform get", "get", result.stderr, result.duration
            )
        return result.success

    @staticmethod
    def _parse_vars(vars: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Parse variable dictionary into command-line arguments.

        Args:
            vars (Dict[str, Any], optional): Dictionary of variable values.
                Defaults to None.

        Returns:
            List[str]: List of formatted variable arguments
        """
        if not vars:
            return []
        args = []
        for key in vars.keys():
            value = vars[key]
            if isinstance(value, str):
                value = re.sub(r"\"", '\\"', value)
                value = f'"{value}"'
            elif (
                isinstance(value, dict)
                or isinstance(value, list)
                or isinstance(value, tuple)
            ):
                value = _json.dumps(value)
            args.append("-var")
            args.append(f"{key}={value}")
        return args

    def plan(
        self,
        out: Optional[str] = None,
        destroy: bool = False,
        refresh: Optional[bool] = True,
        refresh_only: bool = False,
        replace: Optional[str] = None,
        target: Optional[str] = None,
        vars: Optional[dict] = None,
        var_file: Optional[str] = None,
        compact_warnings: bool = False,
        input: Optional[bool] = None,
        json: bool = False,
        lock: Optional[bool] = None,
        lock_timeout: Optional[str] = None,
        color: Optional[bool] = None,
        parallelism: Optional[int] = None,
        chdir: Optional[str] = None,
        state: Optional[str] = None,
    ):
        """Terraform Plan Command

        Args:
            out (str, optional): Writes the generated plan to the given filename in an opaque file format that you can later pass to terraform apply to execute the planned changes. `-out=<filename>` arg Defaults to None.
            destroy (bool, optional): Plan terraform to destroy resources. `-destroy` arg. Defaults to False.
            refresh (bool, optional): Ignore external state changes if false. `-refresh=<true|false>` arg. Defaults to True.
            refresh_only (bool, optional): Only update terraform state. -refresh-only arg. Defaults to False.
            replace (str, optional): Instructs Terraform to plan to replace the resource instance with the given address. `-replace=<value>` arg. Defaults to None.
            target (str, optional): Instructs Terraform to focus its planning efforts only on resource instances which match the given address. `-target=<value>` arg. Defaults to None.
            vars (dict, optional): Dict of vars to pass on CLI. `-var key=value` args in dict format. Defaults to None.
            var_file (str, optional): Path to terraform vars file. `-var-file=<path>` arg. Defaults to None.
            compact_warnings (bool, optional): Shows any warning messages in a compact form. `-compact-warnings` arg. Defaults to False.
            input (bool, optional): Disables Terraform's default behavior of prompting for input for root module input variables that have not otherwise been assigned a value.`-input=<true|false>` arg. Defaults to False.
            json (bool, optional): Enables the machine readable JSON UI output. `-json` arg. Defaults to False.
            lock (bool, optional): Don't hold a state lock during the operation. `-lock=<true|false>` arg. Defaults to None.
            lock_timeout (str, optional): Unless locking is disabled with -lock=false, instructs Terraform to retry acquiring a lock for a period of time before returning an error. `-lock-timeout<int>` arg. Defaults to None.
            color (bool, optional): Enable color output. Defaults to None.
            parallelism (int, optional): Limit the number of concurrent operations as Terraform walks the graph. `-paralellism=<int>` arg. Defaults to 20.
            chdir (str, optional): Directory to run the command at. `-chdir=<path>` arg. Defaults to None.
            state (str, optional): Pass the local state file to plan. `-state=<path>` arg. Defaults to None.

        Raises:
            TerraformPlanError: Terraform Plan Exception

        Returns:
            bool|dict: Returns true if success or the plan output file parsed with 'terraform show -json' command
        """
        cmd = ["plan"]
        cmd.extend(
            self._default_args(
                color=color, lock=lock, lock_timeout=lock_timeout, input=input
            )
        )
        if not out:
            cmd.append(Terraform._build_arg("out", self._planfile))
        else:
            cmd.append(Terraform._build_arg("out", out))

        if (
            self._version["version"]["major"] >= 1
            and self._version["version"]["minor"] >= 0
        ):
            cmd.append(Terraform._build_arg("refresh_only", refresh_only))
        else:
            log.warn(
                f"the option '-refresh-only' is supported since the version 1.1.0, and your version is {self._version['version_str']}"
            )
        if (
            self._version["version"]["major"] >= 1
            and self._version["version"]["minor"] >= 0
        ):
            cmd.append(Terraform._build_arg("json", json))
        else:
            log.warn(
                f"the option '-json' is supported since the version 1.0.0, and your version is {self._version['version_str']}"
            )
        if not parallelism:
            cmd.append(Terraform._build_arg("parallelism", self._paralellism))
        else:
            cmd.append(Terraform._build_arg("parallelism", parallelism))

        cmd.append(Terraform._build_arg("destroy", destroy))
        cmd.append(Terraform._build_arg("refresh", refresh))
        cmd.append(Terraform._build_arg("replace", replace))
        cmd.append(Terraform._build_arg("target", target))
        cmd.append(Terraform._build_arg("var_file", var_file))
        cmd.append(Terraform._build_arg("state", state))
        cmd.append(Terraform._build_arg("compact_warnings", compact_warnings))

        cmd.extend(Terraform._parse_vars(vars))

        if not chdir:
            chdir = self.chdir
        result = Terraform.cmd(cmd, title="Terraform plan", chdir=chdir)
        if result.success:
            log.success(
                f"Terraform plan completed in: {result.duration} seconds")
        else:
            raise TerraformPlanError(
                "Failed to run plan terraform", "plan", result.stderr, result.duration
            )

        return result.success

    @staticmethod
    def _apply_line_callback(stdout: str = None, stderr: str = None):
        """Per line callback for apply command output

        Args:
            stdout (str, optional): Command stdout line. Defaults to None.
            stderr (str, optional): Command stderr line. Defaults to None.
        """
        if stdout:
            stdout = _json.loads(stdout)
            log.info(stdout["@message"])

    @staticmethod
    def _apply_callback(stdout: str = None, stderr: str = None):
        """Output callback for terraform apply

        Args:
            stdout (str, optional): Command result stdout. Defaults to None.
            stderr (str, optional): Command result stderr. Defaults to None.

        Returns:
            dict: Object with parsed info from the apply command in -json mode
        """
        result = {}
        for line in stdout.splitlines():
            try:
                line = _json.loads(line)
                if line["type"] == "outputs":
                    result["outputs"] = line["outputs"]
                elif line["type"] == "change_summary":
                    result["changes"] = line["changes"]
                elif line["type"] == "apply_complete":
                    if not "result" in result:
                        result["result"] = {}
                    addr = line["hook"]["resource"]["addr"]
                    result["result"][addr] = line["hook"]

            except:
                pass
        return result

    def apply(
        self,
        plan_file: Optional[str] = None,
        auto_approve: bool = False,
        compact_warnings: bool = False,
        input: Optional[bool] = None,
        json: bool = False,
        lock: Optional[bool] = None,
        lock_timeout: Optional[str] = None,
        color: Optional[bool] = None,
        parallelism: Optional[int] = None,
        state: Optional[str] = None,
        state_out: Optional[str] = None,
        backup: Optional[str] = None,
        chdir: Optional[str] = None,
    ):
        """Terraform Plan Command

        Args:
            plan_file (str, optional): Plan state file result. Defaults to None.
            auto_approve (bool, optional): Auto approve apply. Defaults to False.
            compact_warnings (bool, optional): Shows any warning messages in a compact form. `-compact-warnings` arg. Defaults to False.
            input (bool, optional): Disables Terraform's default behavior of prompting for input for root module input variables that have not otherwise been assigned a value.`-input=<true|false>` arg. Defaults to False.
            json (bool, optional): Enables the machine readable JSON UI output. `-json` arg. Defaults to False.
            lock (bool, optional): Don't hold a state lock during the operation. `-lock=<true|false>` arg. Defaults to None.
            lock_timeout (str, optional): Unless locking is disabled with -lock=false, instructs Terraform to retry acquiring a lock for a period of time before returning an error. `-lock-timeout<int>` arg. Defaults to None.
            color (bool, optional): Enable color output. Defaults to None.
            parallelism (int, optional): Limit the number of concurrent operations as Terraform walks the graph. `-paralellism=<int>` arg. Defaults to 20.
            state (str, optional): Overrides the state filename when reading the prior state snapshot. `-state=<path>` arg. Defaults to None.
            state_out (str, optional):overrides the state filename when writing new state snapshots. `-state-out=<path>` arg. Defaults to None.
            backup (str, optional): Overrides the default filename that the local backend would normally choose dynamically to create backup files when it writes new state. `-backup=<path>` arg. Defaults to None.
            chdir (str, optional): Directory to run the command at. `-chdir=<path>` arg. Defaults to None.

        Raises:
            TerraformApplyError: Terraform Apply Exception

        Returns:
            Any: Output from callback
        """

        cmd = ["apply"]
        cmd.extend(
            self._default_args(
                color=color, lock=lock, lock_timeout=lock_timeout, input=input
            )
        )

        callback = None
        line_callback = None
        if self._version["version"]["major"] >= 1:
            cmd.append(Terraform._build_arg("json", json))
            if json:
                line_callback = Terraform._apply_line_callback
                callback = Terraform._apply_callback

        if not parallelism:
            cmd.append(Terraform._build_arg("parallelism", self._paralellism))
        else:
            cmd.append(Terraform._build_arg("parallelism", parallelism))
        cmd.append(Terraform._build_arg("auto_approve", auto_approve))
        cmd.append(Terraform._build_arg("compact_warnings", compact_warnings))

        cmd.append(Terraform._build_arg("state", state))
        cmd.append(Terraform._build_arg("state_out", state_out))
        cmd.append(Terraform._build_arg("backup", backup))
        if not plan_file:
            cmd.append(shlex.quote(self._planfile))
        else:
            cmd.append(shlex.quote(plan_file))
        if not chdir:
            chdir = self.chdir
        result = Terraform.cmd(
            cmd,
            title="Terraform apply",
            chdir=chdir,
            line_callback=line_callback,
            callback=callback,
            show_output=not json and self._version["version"]["major"] >= 1,
        )
        if result.success:
            log.success(
                f"Terraform apply completed in: {result.duration} seconds"
            )
        else:
            raise TerraformApplyError(
                "Failed to apply changes to state",
                "apply",
                result.stderr,
                result.duration,
            )
        if json and self._version["version"]["major"] >= 1:
            return result.callback_output
        return result.success

    def destroy(
        self,
        target: Optional[str] = None,
        vars: Optional[Dict[str, Any]] = None,
        var_file: Optional[str] = None,
        auto_approve: bool = False,
        input: Optional[bool] = None,
        color: Optional[bool] = None,
        lock: Optional[bool] = None,
        lock_timeout: Optional[str] = None,
        parallelism: Optional[int] = None,
        chdir: Optional[str] = None,
    ) -> bool:
        """
        Destroy Terraform-managed infrastructure.

        Args:
            target (str, optional): Resource address to target. Defaults to None.
            vars (Dict[str, Any], optional): Dictionary of variable values. Defaults to None.
            var_file (str, optional): Path to variable file. Defaults to None.
            auto_approve (bool): Skip interactive approval. Defaults to False.
            input (bool, optional): Enable interactive input. Defaults to None.
            color (bool, optional): Enable color output. Defaults to None.
            lock (bool, optional): Use state locking. Defaults to None.
            lock_timeout (str, optional): State lock timeout. Defaults to None.
            parallelism (int, optional): Number of parallel operations. Defaults to None.
            chdir (str, optional): Directory to change to before running command. Defaults to None.

        Returns:
            bool: Success status

        Raises:
            TerraformDestroyError: If destroy operation fails
        """
        cmd = ["destroy"]

        cmd.extend(
            self._default_args(
                color=color, lock=lock, lock_timeout=lock_timeout, input=input
            )
        )

        if not parallelism:
            cmd.append(Terraform._build_arg("parallelism", self._paralellism))
        else:
            cmd.append(Terraform._build_arg("parallelism", parallelism))

        cmd.append(Terraform._build_arg("auto_approve", auto_approve))
        cmd.append(Terraform._build_arg("target", target))
        cmd.append(Terraform._build_arg("var_file", var_file))

        cmd.extend(self._parse_vars(vars))

        if not chdir:
            chdir = self.chdir
        result = Terraform.cmd(cmd, title="Terraform destroy", chdir=chdir)
        if result.success:
            log.success(
                f"Terraform destroy completed in: {result.duration} seconds")
            return True
        else:
            error_message = f"Failed to destroy terraform resources"
            log.critical(f"{error_message} in: {result.duration} seconds")
            raise TerraformDestroyError(
                message=error_message,
                command=" ".join(cmd),
                stderr=result.stderr,
                duration=result.duration
            )

    def show(self, file: str = None, json=True, color: bool = None, chdir: str = None):
        """Terraform Show Command

        Args:
            file (str, optional): tfplan file to show. Defaults to last `plan` run output file.
            json (bool, optional): JSON output mode. `-json` arg Defaults to True.
            color (bool, optional): Enable colored output. Defines `-no-color` arg Defaults to None.
            chdir (str, optional): Directory to run the command at. `-chdir=<path>` arg. Defaults to None.

        Returns:
            dict|str: Json result of show command
        """
        cmd = ["show"]
        log.info("Running Terraform show")
        cmd.append(Terraform._build_arg("json", json))

        if color is not None:
            cmd.append(Terraform._build_arg("color", color))
        else:
            cmd.append(Terraform._build_arg("color", self._color))

        if not file:
            cmd.append(shlex.quote(self._planfile))
        else:
            cmd.append(shlex.quote(file))

        if not chdir:
            chdir = self.chdir
        result = Terraform.cmd(cmd, chdir=chdir, show_output=False)
        if result.success:
            log.success(
                f"Terraform show completed in: {result.duration} seconds")
        else:
            log.critical(
                f"Failed to show terraform state in: {result.duration} seconds"
            )
        if json:
            return _json.loads(result.stdout)
        return result.stdout

    def login(self, hostname: str = None, chdir: str = None):
        """Terraform Login Command

        Args:
            hostname (str, optional): Hostname to login. Defaults to None.
            chdir (str, optional): _description_. Defaults to None.

        Raises:
            TerraformLoginError: _description_

        Returns:
            _type_: _description_
        """
        cmd = ["login"]
        if hostname:
            cmd.append(shlex.quote(hostname))

        if not chdir:
            chdir = self.chdir
        result = Terraform.cmd(cmd, title="Terraform login", chdir=chdir)
        if result.success:
            log.success(
                f"Terraform login completed in: {result.duration} seconds"
            )
        else:
            raise TerraformLoginError(
                f"Failed to terraform login to host '{hostname}'",
                "login",
                result.stderr,
                result.duration,
            )
        return result.success

    def logout(self, hostname: str = None, chdir: str = None):
        cmd = ["logout"]
        if hostname:
            cmd.append(shlex.quote(hostname))

        if not chdir:
            chdir = self.chdir
        result = Terraform.cmd(cmd, title="Terraform logout", chdir=chdir)
        if result.success:
            log.success(
                f"Terraform logout completed in: {result.duration} seconds"
            )
        else:
            raise TerraformLogoutError(
                f"Failed to terraform logout to host '{hostname}'",
                "logout",
                result.stderr,
                result.duration,
            )
        return result.success

    @staticmethod
    def fmt(chdir: str = ".", list_files: bool = True, diff: bool = False, write: bool = True, check: bool = False, recursive: bool = False):
        cmd = ["fmt"]
        cmd.append(Terraform._build_arg("diff", diff))
        cmd.append(Terraform._build_arg("check", check))
        cmd.append(Terraform._build_arg("recursive", recursive))
        if list_files is False:
            cmd.append(Terraform._build_arg("list", list_files))
        if write is False:
            cmd.append(Terraform._build_arg("write", write))

        result = Terraform.cmd(cmd, "Terraform fmt", chdir)

        if result.success:
            log.success(f"Terraform fmt completed in {result.duration}s")
        else:
            raise TerraformFmtError(
                "Failed to run terraform fmt", "fmt", result.stderr, result.duration)
        return result.success

    def fmt(self, list_files: bool = True, diff: bool = False, write: bool = True, check: bool = False, recursive: bool = False, chdir: Optional[str] = None):
        cmd = ["fmt"]

        cmd.append(Terraform._build_arg("diff", diff))
        cmd.append(Terraform._build_arg("check", check))
        cmd.append(Terraform._build_arg("recursive", recursive))
        if list_files is False:
            cmd.append(Terraform._build_arg("list", list_files))
        if write is False:
            cmd.append(Terraform._build_arg("write", write))
        if not chdir:
            chdir = self.chdir
        result = Terraform.cmd(cmd, "Terraform fmt", chdir)

        if result.success:
            log.success(f"Terraform fmt completed in {result.duration}s")
        else:
            raise TerraformFmtError(
                "Failed to run terraform fmt", "fmt", result.stderr, result.duration)
        return result.success

    def validate(self, json: Optional[bool] = False, color: Optional[bool] = None, chdir: Optional[str] = None):
        cmd = ["validate"]

        if color is False:
            color = self.color
        cmd.append(Terraform._build_arg("color", color))
        cmd.append(Terraform._build_arg("json", json))
        if not chdir:
            chdir = self.chdir
        result = Terraform.cmd(cmd, "Terraform validate", chdir)

        if result.success:
            log.success(f"Terraform validate completed in {result.duration}s")
        else:
            raise TerraformValidateError(
                "Failed to run terraform validate", "validate", result.stderr, result.duration)
        return result.success

    def output(self, output_name: Optional[str] = None,
               json: Optional[bool] = True,
               raw: Optional[bool] = None,
               color: Optional[bool] = None,
               state: Optional[str] = None,
               chdir: Optional[str] = None):
        cmd = ["output"]
        log.info(cmd)
        if color is False:
            color = self.color
        cmd.append(Terraform._build_arg("color", color))
        cmd.append(Terraform._build_arg("json", json))
        cmd.append(Terraform._build_arg("raw", raw))
        cmd.append(Terraform._build_arg("state", state))
        if output_name:
            cmd.append(shlex.quote(output_name))
        if not chdir:
            chdir = self.chdir
        result = Terraform.cmd(cmd, "Terraform output",
                               chdir, show_output=not json)
        print(result.code)
        if result.success:
            log.success(f"Terraform output completed in {result.duration}s")
        else:
            raise TerraformOutputError(
                "Failed to run terraform output", "output", result.stderr, result.duration)
        if json:
            return _json.loads(result.stdout)
        return result.success

proc=log.start("whole process")
tf = Terraform(chdir="./tests/terraform")
vars = {"bucket_name": "test_bucket",
        "test_variable": {"test1": 1, "test2": None}}
tf.fmt()
log.info(tf.version())
log.info(
    tf.init(
        upgrade=True,
    )
)
tf.validate()
log.info(tf.get())
log.info(tf.plan(vars=vars, destroy=False))
# log.info(tf.show(json=True))
log.info(tf.apply(json=False))
log.info(tf.output(json=True, output_name="pass"))
# log.info(tf.destroy(vars=vars))
log.finish(proc)

