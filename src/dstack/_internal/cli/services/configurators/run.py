import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, TypeVar

import gpuhunt
from pydantic import parse_obj_as

import dstack._internal.core.models.resources as resources
from dstack._internal.cli.services.args import cpu_spec, disk_spec, gpu_spec, port_mapping
from dstack._internal.cli.services.configurators.base import (
    ApplyEnvVarsConfiguratorMixin,
    BaseApplyConfigurator,
)
from dstack._internal.cli.services.profile import apply_profile_args, register_profile_args
from dstack._internal.cli.services.repos import (
    get_repo_from_dir,
    get_repo_from_url,
    init_default_virtual_repo,
    is_git_repo_url,
    register_init_repo_args,
)
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.rich import MultiItemStatus
from dstack._internal.cli.utils.run import get_runs_table, print_run_plan
from dstack._internal.core.errors import (
    CLIError,
    ConfigurationError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.common import ApplyAction, RegistryAuth
from dstack._internal.core.models.configurations import (
    AnyRunConfiguration,
    ApplyConfigurationType,
    ConfigurationWithCommandsParams,
    ConfigurationWithPortsParams,
    DevEnvironmentConfiguration,
    PortMapping,
    RunConfigurationType,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.repos import RepoHeadWithCreds
from dstack._internal.core.models.repos.remote import RemoteRepo, RemoteRepoCreds
from dstack._internal.core.models.resources import CPUSpec
from dstack._internal.core.models.runs import JobStatus, JobSubmission, RunSpec, RunStatus
from dstack._internal.core.services.diff import diff_models
from dstack._internal.core.services.repos import (
    InvalidRepoCredentialsError,
    get_repo_creds_and_default_branch,
)
from dstack._internal.utils.common import local_time
from dstack._internal.utils.interpolator import InterpolatorError, VariablesInterpolator
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.nested_list import NestedList, NestedListItem
from dstack._internal.utils.path import is_absolute_posix_path
from dstack.api._public.runs import Run
from dstack.api.utils import load_profile

_KNOWN_AMD_GPUS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_AMD_GPUS}
_KNOWN_NVIDIA_GPUS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_NVIDIA_GPUS}
_KNOWN_TPU_VERSIONS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_TPUS}
_KNOWN_TENSTORRENT_GPUS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_TENSTORRENT_ACCELERATORS}
_BIND_ADDRESS_ARG = "bind_address"

logger = get_logger(__name__)

RunConfigurationT = TypeVar("RunConfigurationT", bound=AnyRunConfiguration)


class BaseRunConfigurator(
    ApplyEnvVarsConfiguratorMixin,
    BaseApplyConfigurator[RunConfigurationT],
):
    def apply_configuration(
        self,
        conf: RunConfigurationT,
        configuration_path: str,
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
    ):
        if configurator_args.repo and configurator_args.no_repo:
            raise CLIError("Either --repo or --no-repo can be specified")

        self.apply_args(conf, configurator_args)
        self.validate_gpu_vendor_and_image(conf)
        self.validate_cpu_arch_and_image(conf)

        if conf.working_dir is not None and not is_absolute_posix_path(conf.working_dir):
            raise ConfigurationError("working_dir must be absolute")

        repo = self.get_repo(conf, configuration_path, configurator_args)
        if repo is None:
            repo = init_default_virtual_repo(api=self.api)
        profile = load_profile(Path.cwd(), configurator_args.profile)
        with console.status("Getting apply plan..."):
            run_plan = self.api.runs.get_run_plan(
                configuration=conf,
                repo=repo,
                configuration_path=configuration_path,
                profile=profile,
                ssh_identity_file=configurator_args.ssh_identity_file,
            )

        no_fleets = False
        if len(run_plan.job_plans[0].offers) == 0:
            if len(self.api.client.fleets.list(self.api.project)) == 0:
                no_fleets = True

        print_run_plan(run_plan, max_offers=configurator_args.max_offers, no_fleets=no_fleets)

        confirm_message = "Submit a new run?"
        if conf.name:
            confirm_message = f"Submit the run [code]{conf.name}[/]?"
        stop_run_name = None
        if run_plan.current_resource is not None:
            diff = render_run_spec_diff(
                run_plan.get_effective_run_spec(),
                run_plan.current_resource.run_spec,
            )
            if run_plan.action == ApplyAction.UPDATE and diff is not None:
                console.print(
                    f"Active run [code]{conf.name}[/] already exists."
                    f" Detected changes that [code]can[/] be updated in-place:\n{diff}"
                )
                confirm_message = "Update the run?"
            elif run_plan.action == ApplyAction.UPDATE and diff is None:
                stop_run_name = run_plan.current_resource.run_spec.run_name
                console.print(
                    f"Active run [code]{conf.name}[/] already exists. Detected no changes."
                )
                if command_args.yes and not command_args.force:
                    console.print("Use --force to apply anyway.")
                    return
                confirm_message = "Stop and override the run?"
            elif not run_plan.current_resource.status.is_finished():
                stop_run_name = run_plan.current_resource.run_spec.run_name
                console.print(
                    f"Active run [code]{conf.name}[/] already exists."
                    f" Detected changes that [error]cannot[/] be updated in-place:\n{diff}"
                )
                confirm_message = "Stop and override the run?"

        if not command_args.yes and not confirm_ask(confirm_message):
            console.print("\nExiting...")
            return

        if stop_run_name is not None:
            with console.status("Stopping run..."):
                self.api.client.runs.stop(self.api.project, [stop_run_name], abort=False)
                while True:
                    run = self.api.runs.get(stop_run_name)
                    if run is None or run.status.is_finished():
                        break
                    time.sleep(1)

        try:
            with console.status("Applying plan..."):
                run = self.api.runs.apply_plan(
                    run_plan=run_plan, repo=repo, reserve_ports=not command_args.detach
                )
        except ServerClientError as e:
            raise CLIError(e.msg)

        if command_args.detach:
            detach_message = f"Run [code]{run.name}[/] submitted, detaching..."
            if run_plan.action == ApplyAction.UPDATE:
                detach_message = f"Run [code]{run.name}[/] updated, detaching..."
            console.print(detach_message)
            return

        abort_at_exit = False
        try:
            # We can attach to run multiple times if it goes from running to pending (retried).
            while True:
                with MultiItemStatus(f"Launching [code]{run.name}[/]...", console=console) as live:
                    while not _is_ready_to_attach(run):
                        table = get_runs_table([run])
                        live.update(table)
                        time.sleep(5)
                        run.refresh()

                console.print(
                    get_runs_table(
                        [run],
                        verbose=run.status == RunStatus.FAILED,
                        format_date=local_time,
                    )
                )

                console.print(
                    f"\n[code]{run.name}[/] provisioning completed [secondary]({run.status.value})[/]"
                )

                current_job_submission = run._run.latest_job_submission
                if run.status in (RunStatus.RUNNING, RunStatus.DONE):
                    _print_service_urls(run)
                    bind_address: Optional[str] = getattr(
                        configurator_args, _BIND_ADDRESS_ARG, None
                    )
                    try:
                        if run.attach(bind_address=bind_address):
                            for entry in run.logs():
                                sys.stdout.buffer.write(entry)
                                sys.stdout.buffer.flush()
                        else:
                            console.print("[error]Failed to attach, exiting...[/]")
                            exit(1)
                    finally:
                        run.detach()

                # After reading the logs, the run may not be marked as finished immediately.
                # Give the run some time to transition to a finished state before exiting.
                reattach = False
                for _ in range(30):
                    run.refresh()
                    if _run_resubmitted(run, current_job_submission):
                        # The run was resubmitted
                        reattach = True
                        break
                    if run.status.is_finished():
                        print_finished_message(run)
                        exit(get_run_exit_code(run))
                    time.sleep(1)
                if not reattach:
                    console.print(
                        "[error]Lost run connection. Timed out waiting for run final status."
                        " Check `dstack ps` to see if it's done or failed."
                    )
                    exit(1)
        except KeyboardInterrupt:
            try:
                if command_args.yes or not confirm_ask(
                    f"\nStop the run [code]{run.name}[/] before detaching?"
                ):
                    console.print("Detached")
                    abort_at_exit = False
                    return
                # Gently stop the run and wait for it to finish
                with console.status("Stopping..."):
                    run.stop(abort=False)
                    while not run.status.is_finished():
                        time.sleep(2)
                        run.refresh()
                console.print("Stopped")
            except KeyboardInterrupt:
                abort_at_exit = True
        finally:
            run.detach()
            if abort_at_exit:
                with console.status("Aborting..."):
                    run.stop(abort=True)
                console.print("[error]Aborted[/]")

    def delete_configuration(
        self,
        conf: RunConfigurationT,
        configuration_path: str,
        command_args: argparse.Namespace,
    ):
        if conf.name is None:
            console.print("[error]Configuration specifies no run to delete[/]")
            exit(1)
        try:
            self.api.client.runs.get(
                project_name=self.api.project,
                run_name=conf.name,
            )
        except ResourceNotExistsError:
            console.print(f"Run [code]{conf.name}[/] does not exist")
            exit(1)
        if not command_args.yes and not confirm_ask(f"Delete the run [code]{conf.name}[/]?"):
            console.print("\nExiting...")
            return
        with console.status("Deleting run..."):
            self.api.client.runs.delete(
                project_name=self.api.project,
                runs_names=[conf.name],
            )
        console.print(f"Run [code]{conf.name}[/] deleted")

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        parser.add_argument(
            "--ssh-identity",
            metavar="SSH_PRIVATE_KEY",
            help="The private SSH key path for SSH tunneling",
            type=Path,
            dest="ssh_identity_file",
        )
        configuration_group = parser.add_argument_group(f"{cls.TYPE.value} Options")
        configuration_group.add_argument(
            "-n",
            "--name",
            dest="run_name",
            help="The name of the run. If not specified, a random name is assigned",
        )
        configuration_group.add_argument(
            "--max-offers",
            help="Number of offers to show in the run plan",
            type=int,
            default=3,
        )
        cls.register_env_args(configuration_group)
        configuration_group.add_argument(
            "--cpu",
            type=cpu_spec,
            help="Request CPU for the run. "
            "The format is [code]ARCH[/]:[code]COUNT[/] (all parts are optional)",
            dest="cpu_spec",
            metavar="SPEC",
        )
        configuration_group.add_argument(
            "--gpu",
            type=gpu_spec,
            help="Request GPU for the run. "
            "The format is [code]NAME[/]:[code]COUNT[/]:[code]MEMORY[/] (all parts are optional)",
            dest="gpu_spec",
            metavar="SPEC",
        )
        configuration_group.add_argument(
            "--disk",
            type=disk_spec,
            help="Request the size range of disk for the run. Example [code]--disk 100GB..[/].",
            metavar="RANGE",
            dest="disk_spec",
        )
        register_profile_args(parser)
        repo_group = parser.add_argument_group("Repo Options")
        repo_group.add_argument(
            "-P",
            "--repo",
            help=("The repo to use for the run. Can be a local path or a Git repo URL."),
            dest="repo",
        )
        repo_group.add_argument(
            "--repo-branch",
            help="The repo branch to use for the run",
            dest="repo_branch",
        )
        repo_group.add_argument(
            "--repo-hash",
            help="The hash of the repo commit to use for the run",
            dest="repo_hash",
        )
        repo_group.add_argument(
            "--no-repo",
            help="Do not use any repo for the run",
            dest="no_repo",
            action="store_true",
        )
        register_init_repo_args(repo_group)

    def apply_args(self, conf: RunConfigurationT, args: argparse.Namespace):
        apply_profile_args(args, conf)
        if args.run_name:
            conf.name = args.run_name
        if args.cpu_spec:
            conf.resources.cpu = resources.CPUSpec.parse_obj(args.cpu_spec)
        if args.gpu_spec:
            conf.resources.gpu = resources.GPUSpec.parse_obj(args.gpu_spec)
        if args.disk_spec:
            conf.resources.disk = args.disk_spec

        self.apply_env_vars(conf.env, args)
        self.interpolate_env(conf)

    def interpolate_env(self, conf: RunConfigurationT):
        env_dict = conf.env.as_dict()
        interpolator = VariablesInterpolator({"env": env_dict}, skip=["secrets"])
        try:
            if conf.registry_auth is not None:
                conf.registry_auth = RegistryAuth(
                    username=interpolator.interpolate_or_error(conf.registry_auth.username),
                    password=interpolator.interpolate_or_error(conf.registry_auth.password),
                )
            if isinstance(conf, ServiceConfiguration):
                for probe in conf.probes:
                    for header in probe.headers:
                        header.value = interpolator.interpolate_or_error(header.value)
                    if probe.url:
                        probe.url = interpolator.interpolate_or_error(probe.url)
                    if probe.body:
                        probe.body = interpolator.interpolate_or_error(probe.body)
        except InterpolatorError as e:
            raise ConfigurationError(e.args[0])

    def validate_gpu_vendor_and_image(self, conf: RunConfigurationT) -> None:
        """
        Infers and sets `resources.gpu.vendor` if not set, requires `image` if the vendor is AMD.
        """
        gpu_spec = conf.resources.gpu
        if gpu_spec is None:
            return
        if gpu_spec.count.max == 0:
            return
        has_amd_gpu: bool
        has_tt_gpu: bool
        vendor = gpu_spec.vendor
        if vendor is None:
            names = gpu_spec.name
            if names:
                # None is a placeholder for an unknown vendor.
                vendors: Set[Optional[gpuhunt.AcceleratorVendor]] = set()
                for name in names:
                    name = name.lower()
                    if name in _KNOWN_NVIDIA_GPUS:
                        vendors.add(gpuhunt.AcceleratorVendor.NVIDIA)
                    elif name in _KNOWN_AMD_GPUS:
                        vendors.add(gpuhunt.AcceleratorVendor.AMD)
                    elif name in _KNOWN_TENSTORRENT_GPUS:
                        vendors.add(gpuhunt.AcceleratorVendor.TENSTORRENT)
                    else:
                        maybe_tpu_version, _, maybe_tpu_cores = name.partition("-")
                        if maybe_tpu_version in _KNOWN_TPU_VERSIONS and maybe_tpu_cores.isdigit():
                            vendors.add(gpuhunt.AcceleratorVendor.GOOGLE)
                        else:
                            vendors.add(None)
                if len(vendors) == 1:
                    # Only one vendor or all names are not known.
                    vendor = next(iter(vendors))
                else:
                    # More than one vendor or some names are not known; in either case, we
                    # cannot set the vendor to a specific value, will use only names for matching.
                    vendor = None
                # If some names are unknown, let's assume they are _not_ AMD products, otherwise
                # ConfigurationError message may be confusing. In worst-case scenario we'll try
                # to execute a run on an instance with an AMD accelerator with a default
                # CUDA image, not a big deal.
                has_amd_gpu = gpuhunt.AcceleratorVendor.AMD in vendors
                has_tt_gpu = gpuhunt.AcceleratorVendor.TENSTORRENT in vendors
            else:
                # If neither gpu.vendor nor gpu.name is set, assume Nvidia.
                vendor = gpuhunt.AcceleratorVendor.NVIDIA
                has_amd_gpu = False
                has_tt_gpu = False
            gpu_spec.vendor = vendor
        else:
            has_amd_gpu = vendor == gpuhunt.AcceleratorVendor.AMD
            has_tt_gpu = vendor == gpuhunt.AcceleratorVendor.TENSTORRENT
        # When docker=True, the system uses Docker-in-Docker image, so no custom image is required
        if has_amd_gpu and conf.image is None and conf.docker is not True:
            raise ConfigurationError("`image` is required if `resources.gpu.vendor` is `amd`")
        if has_tt_gpu and conf.image is None and conf.docker is not True:
            raise ConfigurationError(
                "`image` is required if `resources.gpu.vendor` is `tenstorrent`"
            )

    def validate_cpu_arch_and_image(self, conf: RunConfigurationT) -> None:
        """
        Infers `resources.cpu.arch` if not set, requires `image` if the architecture is ARM.
        """
        # TODO: Remove in 0.20. Use conf.resources.cpu directly
        cpu_spec = parse_obj_as(CPUSpec, conf.resources.cpu)
        arch = cpu_spec.arch
        if arch is None:
            gpu_spec = conf.resources.gpu
            if (
                gpu_spec is not None
                and gpu_spec.vendor in [None, gpuhunt.AcceleratorVendor.NVIDIA]
                and gpu_spec.name
                and any(map(gpuhunt.is_nvidia_superchip, gpu_spec.name))
            ):
                arch = gpuhunt.CPUArchitecture.ARM
            else:
                arch = gpuhunt.CPUArchitecture.X86
        # NOTE: We don't set the inferred resources.cpu.arch for compatibility with older servers.
        # Servers with ARM support set the arch using the same logic.
        if arch == gpuhunt.CPUArchitecture.ARM and conf.image is None:
            raise ConfigurationError("`image` is required if `resources.cpu.arch` is `arm`")

    def get_repo(
        self,
        conf: RunConfigurationT,
        configuration_path: str,
        configurator_args: argparse.Namespace,
    ) -> Optional[RemoteRepo]:
        if configurator_args.no_repo:
            return None

        repo: Optional[RemoteRepo] = None
        repo_head: Optional[RepoHeadWithCreds] = None
        repo_branch: Optional[str] = configurator_args.repo_branch
        repo_hash: Optional[str] = configurator_args.repo_hash
        repo_creds: Optional[RemoteRepoCreds] = None
        git_identity_file: Optional[str] = configurator_args.git_identity_file
        git_private_key: Optional[str] = None
        oauth_token: Optional[str] = configurator_args.gh_token
        # Should we (re)initialize the repo?
        # If any Git credentials provided, we reinitialize the repo, as the user may have provided
        # updated credentials.
        init = git_identity_file is not None or oauth_token is not None

        url: Optional[str] = None
        local_path: Optional[Path] = None
        # dummy value, safe to join with any path
        root_dir = Path(".")
        if repo_arg := configurator_args.repo:
            if is_git_repo_url(repo_arg):
                url = repo_arg
            else:
                local_path = Path(repo_arg)
                # rel paths in `--repo` are resolved relative to the current working dir
                root_dir = Path.cwd()
        elif conf.repos:
            repo_spec = conf.repos[0]
            if repo_spec.url:
                url = repo_spec.url
            elif repo_spec.local_path:
                local_path = Path(repo_spec.local_path)
                # rel paths in the conf are resolved relative to the conf's parent dir
                root_dir = Path(configuration_path).resolve().parent
            else:
                assert False, f"should not reach here: {repo_spec}"
            if repo_branch is None:
                repo_branch = repo_spec.branch
            if repo_hash is None:
                repo_hash = repo_spec.hash
        else:
            return None

        if url:
            repo = get_repo_from_url(url)
            repo_head = self.api.repos.get(repo_id=repo.repo_id, with_creds=True)
        elif local_path:
            original_local_path = local_path
            local_path = local_path.expanduser()
            if not local_path.is_absolute():
                local_path = (root_dir / local_path).resolve()
            if not local_path.exists():
                raise ConfigurationError(
                    f"Invalid repo path: {original_local_path} -> {local_path}"
                )
            repo = get_repo_from_dir(local_path)
            repo_head = self.api.repos.get(repo_id=repo.repo_id, with_creds=True)
            repo_branch = repo.run_repo_data.repo_branch
            repo_hash = repo.run_repo_data.repo_hash
        else:
            assert False, "should not reach here"

        assert repo.repo_url is not None

        if repo_head is not None and repo_head.repo_creds is not None:
            if git_identity_file is None and oauth_token is None:
                git_private_key = repo_head.repo_creds.private_key
                oauth_token = repo_head.repo_creds.oauth_token
        else:
            init = True

        try:
            repo_creds, _ = get_repo_creds_and_default_branch(
                repo_url=repo.repo_url,
                identity_file=git_identity_file,
                private_key=git_private_key,
                oauth_token=oauth_token,
            )
        except InvalidRepoCredentialsError as e:
            raise CLIError(*e.args) from e

        repo.run_repo_data.repo_branch = repo_branch
        if repo_hash is not None:
            repo.run_repo_data.repo_hash = repo_hash

        if init:
            self.api.repos.init(
                repo=repo,
                git_identity_file=git_identity_file,
                oauth_token=oauth_token,
                creds=repo_creds,
            )

        return repo


class RunWithPortsConfiguratorMixin:
    @classmethod
    def register_ports_args(cls, parser: argparse.ArgumentParser):
        parser.add_argument(
            "-p",
            "--port",
            type=port_mapping,
            action="append",
            help="Exposed port or mapping",
            dest="ports",
            metavar="MAPPING",
        )
        parser.add_argument(
            "--host",
            help="Local address to bind. Defaults to [code]localhost[/]",
            dest=_BIND_ADDRESS_ARG,
            metavar="HOST",
        )

    def apply_ports_args(
        self,
        conf: ConfigurationWithPortsParams,
        args: argparse.Namespace,
    ):
        if args.ports:
            conf.ports = list(_merge_ports(conf.ports, args.ports).values())


class RunWithCommandsConfiguratorMixin:
    @classmethod
    def register_commands_args(cls, parser: argparse.ArgumentParser):
        parser.add_argument(
            "run_args",
            help=(
                "Run arguments. Available in the configuration [code]commands[/code] as"
                " [code]${{ run.args }}[/code]."
                " Use [code]--[/code] to separate run options from [code]dstack[/code] options"
            ),
            nargs="*",
            metavar="RUN_ARGS",
        )

    def apply_commands_args(
        self,
        conf: ConfigurationWithCommandsParams,
        args: argparse.Namespace,
    ):
        commands = conf.commands
        run_args = shlex.join(args.run_args)
        interpolator = VariablesInterpolator({"run": {"args": run_args}}, skip=["secrets"])
        try:
            for i, command in enumerate(commands):
                commands[i] = interpolator.interpolate_or_error(command)
        except InterpolatorError as e:
            raise ConfigurationError(e.args[0])


class TaskConfigurator(
    RunWithPortsConfiguratorMixin, RunWithCommandsConfiguratorMixin, BaseRunConfigurator
):
    TYPE = ApplyConfigurationType.TASK

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        super().register_args(parser)
        cls.register_ports_args(parser)
        cls.register_commands_args(parser)

    def apply_args(self, conf: TaskConfiguration, args: argparse.Namespace):
        super().apply_args(conf, args)
        self.apply_ports_args(conf, args)
        self.apply_commands_args(conf, args)


class DevEnvironmentConfigurator(RunWithPortsConfiguratorMixin, BaseRunConfigurator):
    TYPE = ApplyConfigurationType.DEV_ENVIRONMENT

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        super().register_args(parser)
        cls.register_ports_args(parser)

    def apply_args(self, conf: DevEnvironmentConfiguration, args: argparse.Namespace):
        super().apply_args(conf, args)
        self.apply_ports_args(conf, args)
        if conf.ide == "vscode" and conf.version is None:
            conf.version = _detect_vscode_version()
            if conf.version is None:
                console.print(
                    "[secondary]Unable to detect the VS Code version and pre-install extensions. "
                    "Fix by opening [code]Command Palette[/code], executing [code]Shell Command: "
                    "Install 'code' command in PATH[/code], and restarting terminal.[/]\n"
                )
        if conf.ide == "cursor" and conf.version is None:
            conf.version = _detect_cursor_version()
            if conf.version is None:
                console.print(
                    "[secondary]Unable to detect the Cursor version and pre-install extensions. "
                    "Fix by opening [code]Command Palette[/code], executing [code]Shell Command: "
                    "Install 'cursor' command in PATH[/code], and restarting terminal.[/]\n"
                )


class ServiceConfigurator(RunWithCommandsConfiguratorMixin, BaseRunConfigurator):
    TYPE = ApplyConfigurationType.SERVICE

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        super().register_args(parser)
        cls.register_commands_args(parser)

    def apply_args(self, conf: TaskConfiguration, args: argparse.Namespace):
        super().apply_args(conf, args)
        self.apply_commands_args(conf, args)


def _merge_ports(conf: List[PortMapping], args: List[PortMapping]) -> Dict[int, PortMapping]:
    _unique_ports_constraint([pm.container_port for pm in conf])
    _unique_ports_constraint([pm.container_port for pm in args])
    ports = {pm.container_port: pm for pm in conf}
    for pm in args:  # override conf
        ports[pm.container_port] = pm
    _unique_ports_constraint([pm.local_port for pm in ports.values() if pm.local_port is not None])
    return ports


def _unique_ports_constraint(ports: List[int]):
    used_ports = set()
    for i in ports:
        if i in used_ports:
            raise ConfigurationError(f"Port {i} is already in use")
        used_ports.add(i)


def _detect_vscode_version(exe: str = "code") -> Optional[str]:
    try:
        run = subprocess.run([exe, "--version"], capture_output=True)
    except FileNotFoundError:
        return None
    if run.returncode == 0:
        return run.stdout.decode().split("\n")[1].strip()
    return None


def _detect_cursor_version(exe: str = "cursor") -> Optional[str]:
    try:
        run = subprocess.run([exe, "--version"], capture_output=True)
    except FileNotFoundError:
        return None
    if run.returncode == 0:
        return run.stdout.decode().split("\n")[1].strip()
    return None


def _print_service_urls(run: Run) -> None:
    if run._run.run_spec.configuration.type != RunConfigurationType.SERVICE.value:
        return
    console.print(f"Service is published at:\n  [link={run.service_url}]{run.service_url}[/]")
    if model := run.service_model:
        console.print(
            f"Model [code]{model.name}[/] is published at:\n  [link={model.url}]{model.url}[/]"
        )
    console.print()


def print_finished_message(run: Run):
    status_message = (
        run._run.latest_job_submission.status_message
        if run._run.latest_job_submission
        else run._run.status_message
    )
    error = (
        run._run.latest_job_submission.error if run._run.latest_job_submission else run._run.error
    )
    termination_reason = (
        run._run.latest_job_submission.termination_reason
        if run._run.latest_job_submission
        else None
    )
    termination_reason_message = (
        run._run.latest_job_submission.termination_reason_message
        if run._run.latest_job_submission
        else None
    )
    if run.status == RunStatus.DONE:
        console.print(f"[code]{status_message.capitalize()}[/code]")
        return
    else:
        str = f"[error]{status_message.capitalize()}[/error]"
        if error:
            str += f" ([error]{error.capitalize()}[/error])"
        console.print(str)

        if termination_reason_message:
            console.print(f"[error]{termination_reason_message}[/error]")

        if termination_reason:
            console.print(f"Check [code]dstack logs -d {run.name}[/code] for more details.")


def get_run_exit_code(run: Run) -> int:
    if run.status == RunStatus.DONE:
        return 0
    return 1


def _is_ready_to_attach(run: Run) -> bool:
    return not (
        run.status
        in [
            RunStatus.SUBMITTED,
            RunStatus.PENDING,
            RunStatus.PROVISIONING,
            RunStatus.TERMINATING,
        ]
        or run._run.jobs[0].job_submissions[-1].status
        in [JobStatus.SUBMITTED, JobStatus.PROVISIONING, JobStatus.PULLING]
        or run._run.is_deployment_in_progress()
    )


def _run_resubmitted(run: Run, current_job_submission: Optional[JobSubmission]) -> bool:
    if current_job_submission is None or run._run.latest_job_submission is None:
        return False
    return run.status == RunStatus.PENDING or (
        not run.status.is_finished()
        and run._run.latest_job_submission.submitted_at > current_job_submission.submitted_at
    )


def render_run_spec_diff(old_spec: RunSpec, new_spec: RunSpec) -> Optional[str]:
    changed_spec_fields = list(diff_models(old_spec, new_spec))
    if not changed_spec_fields:
        return None
    friendly_spec_field_names = {
        "repo_id": "Repo ID",
        "repo_code_hash": "Repo files",
        "repo_data": "Repo state (branch, commit, or other)",
        "ssh_key_pub": "Public SSH key",
    }
    nested_list = NestedList()
    for spec_field in changed_spec_fields:
        if spec_field == "merged_profile":
            continue
        elif spec_field == "configuration":
            if type(old_spec.configuration) is not type(new_spec.configuration):
                item = NestedListItem("Configuration type")
            else:
                item = NestedListItem(
                    "Configuration properties:",
                    children=[
                        NestedListItem(field)
                        for field in diff_models(old_spec.configuration, new_spec.configuration)
                    ],
                )
        elif spec_field == "profile":
            if type(old_spec.profile) is not type(new_spec.profile):
                item = NestedListItem("Profile")
            else:
                assert old_spec.profile is not None
                assert new_spec.profile is not None
                item = NestedListItem(
                    "Profile properties:",
                    children=[
                        NestedListItem(field)
                        for field in diff_models(old_spec.profile, new_spec.profile)
                    ],
                )
        elif spec_field in friendly_spec_field_names:
            item = NestedListItem(friendly_spec_field_names[spec_field])
        else:
            item = NestedListItem(spec_field.replace("_", " ").capitalize())
        nested_list.children.append(item)
    return nested_list.render()
