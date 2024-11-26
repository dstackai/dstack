import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import gpuhunt

import dstack._internal.core.models.resources as resources
from dstack._internal.cli.services.args import disk_spec, gpu_spec, port_mapping
from dstack._internal.cli.services.configurators.base import (
    ApplyEnvVarsConfiguratorMixin,
    BaseApplyConfigurator,
)
from dstack._internal.cli.services.profile import apply_profile_args, register_profile_args
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.run import print_run_plan
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
    BaseRunConfiguration,
    BaseRunConfigurationWithPorts,
    DevEnvironmentConfiguration,
    PortMapping,
    PythonVersion,
    RunConfigurationType,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.runs import JobSubmission, JobTerminationReason, RunStatus
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.diff import diff_models
from dstack._internal.utils.interpolator import InterpolatorError, VariablesInterpolator
from dstack._internal.utils.logging import get_logger
from dstack.api._public.runs import Run
from dstack.api.utils import load_profile

_KNOWN_AMD_GPUS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_AMD_GPUS}
_KNOWN_NVIDIA_GPUS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_NVIDIA_GPUS}
_KNOWN_TPU_VERSIONS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_TPUS}

_BIND_ADDRESS_ARG = "bind_address"

logger = get_logger(__name__)


class BaseRunConfigurator(ApplyEnvVarsConfiguratorMixin, BaseApplyConfigurator):
    TYPE: ApplyConfigurationType

    def apply_configuration(
        self,
        conf: BaseRunConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
        unknown_args: List[str],
    ):
        self.apply_args(conf, configurator_args, unknown_args)
        self.validate_gpu_vendor_and_image(conf)
        if conf.python == PythonVersion.PY38:
            logger.warning(
                "Specifying [code]python: 3.8[/] in run configurations is deprecated"
                " and will be forbidden in a future [code]dstack[/] release."
                " Please upgrade your configuration to a newer Python version."
            )
        repo = self.api.repos.load(Path.cwd())
        repo_config = ConfigManager().get_repo_config_or_error(repo.get_repo_dir_or_error())
        self.api.ssh_identity_file = repo_config.ssh_key_path
        profile = load_profile(Path.cwd(), configurator_args.profile)
        with console.status("Getting apply plan..."):
            run_plan = self.api.runs.get_plan(
                configuration=conf,
                repo=repo,
                configuration_path=configuration_path,
                backends=profile.backends,
                regions=profile.regions,
                instance_types=profile.instance_types,
                spot_policy=profile.spot_policy,
                retry_policy=profile.retry_policy,
                max_duration=profile.max_duration,
                max_price=profile.max_price,
                working_dir=conf.working_dir,
                run_name=conf.name,
                pool_name=profile.pool_name,
                instance_name=profile.instance_name,
                creation_policy=profile.creation_policy,
                termination_policy=profile.termination_policy,
                termination_policy_idle=profile.termination_idle_time,
            )

        print_run_plan(run_plan, offers_limit=configurator_args.max_offers)

        confirm_message = "Submit a new run?"
        stop_run_name = None
        if run_plan.current_resource is not None:
            diff = diff_models(
                run_plan.run_spec.configuration, run_plan.current_resource.run_spec.configuration
            )
            changed_fields = list(diff.keys())
            if run_plan.action == ApplyAction.UPDATE and len(changed_fields) > 0:
                console.print(
                    f"Active run [code]{conf.name}[/] already exists."
                    " Detected configuration changes that can be updated in-place:"
                    f" {changed_fields}"
                )
                confirm_message = "Update the run?"
            elif run_plan.action == ApplyAction.UPDATE and len(changed_fields) == 0:
                stop_run_name = run_plan.current_resource.run_spec.run_name
                console.print(
                    f"Active run [code]{conf.name}[/] already exists."
                    " Detected no configuration changes."
                )
                if command_args.yes and not command_args.force:
                    console.print("Use --force to apply anyway.")
                    return
                confirm_message = "Stop and override the run?"
            elif not run_plan.current_resource.status.is_finished():
                stop_run_name = run_plan.current_resource.run_spec.run_name
                console.print(
                    f"Active run [code]{conf.name}[/] already exists and cannot be updated in-place."
                )
                confirm_message = "Stop and override the run?"
            else:
                console.print(f"Finished run [code]{conf.name}[/] already exists.")
                confirm_message = "Override the run?"
        elif conf.name:
            confirm_message = f"Submit the run [code]{conf.name}[/]?"

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
                run = self.api.runs.exec_plan(
                    run_plan, repo, reserve_ports=not command_args.detach
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
                with console.status(f"Launching [code]{run.name}[/]") as status:
                    while run.status in (
                        RunStatus.SUBMITTED,
                        RunStatus.PENDING,
                        RunStatus.PROVISIONING,
                    ):
                        job_statuses = "\n".join(
                            f"  - {job.job_spec.job_name} [secondary]({job.job_submissions[-1].status.value})[/]"
                            for job in run._run.jobs
                        )
                        status.update(
                            f"Launching [code]{run.name}[/] [secondary]({run.status.value})[/]\n{job_statuses}"
                        )
                        time.sleep(5)
                        run.refresh()
                console.print(
                    f"[code]{run.name}[/] provisioning completed [secondary]({run.status.value})[/]"
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
                # Give the run some time to transit into a finished state before exiting.
                reattach = False
                for _ in range(30):
                    run.refresh()
                    if _run_resubmitted(run, current_job_submission):
                        # The run was resubmitted
                        reattach = True
                        break
                    if run.status.is_finished():
                        _print_finished_message(run)
                        exit(_get_run_exit_code(run))
                    time.sleep(1)
                if not reattach:
                    console.print(
                        "[error]Lost run connection. Timed out waiting for run final status."
                        " Check `dstack ps` to see if it's done or failed."
                    )
                    exit(1)
        except KeyboardInterrupt:
            try:
                if not confirm_ask(f"\nStop the run [code]{run.name}[/] before detaching?"):
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
        conf: AnyRunConfiguration,
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
            "-n",
            "--name",
            dest="run_name",
            help="The name of the run. If not specified, a random name is assigned",
        )
        parser.add_argument(
            "--max-offers",
            help="Number of offers to show in the run plan",
            type=int,
            default=3,
        )
        cls.register_env_args(parser)
        parser.add_argument(
            "--gpu",
            type=gpu_spec,
            help="Request GPU for the run. "
            "The format is [code]NAME[/]:[code]COUNT[/]:[code]MEMORY[/] (all parts are optional)",
            dest="gpu_spec",
            metavar="SPEC",
        )
        parser.add_argument(
            "--disk",
            type=disk_spec,
            help="Request the size range of disk for the run. Example [code]--disk 100GB..[/].",
            metavar="RANGE",
            dest="disk_spec",
        )
        register_profile_args(parser)

    def apply_args(self, conf: BaseRunConfiguration, args: argparse.Namespace, unknown: List[str]):
        apply_profile_args(args, conf)
        if args.run_name:
            conf.name = args.run_name
        if args.gpu_spec:
            conf.resources.gpu = resources.GPUSpec.parse_obj(args.gpu_spec)
        if args.disk_spec:
            conf.resources.disk = args.disk_spec

        self.apply_env_vars(conf.env, args)
        self.interpolate_env(conf)
        self.interpolate_run_args(conf.setup, unknown)

    def interpolate_run_args(self, value: List[str], unknown):
        run_args = " ".join(unknown)
        interpolator = VariablesInterpolator({"run": {"args": run_args}}, skip=["secrets"])
        try:
            for i in range(len(value)):
                value[i] = interpolator.interpolate_or_error(value[i])
        except InterpolatorError as e:
            raise ConfigurationError(e.args[0])

    def interpolate_env(self, conf: BaseRunConfiguration):
        env_dict = conf.env.as_dict()
        interpolator = VariablesInterpolator({"env": env_dict}, skip=["secrets"])
        try:
            if conf.registry_auth is not None:
                conf.registry_auth = RegistryAuth(
                    username=interpolator.interpolate_or_error(conf.registry_auth.username),
                    password=interpolator.interpolate_or_error(conf.registry_auth.password),
                )
        except InterpolatorError as e:
            raise ConfigurationError(e.args[0])

    def validate_gpu_vendor_and_image(self, conf: BaseRunConfiguration) -> None:
        """
        Infers `resources.gpu.vendor` if not set, requires `image` if the vendor is AMD.
        """
        gpu_spec = conf.resources.gpu
        if gpu_spec is None:
            return
        if gpu_spec.count.max == 0:
            return
        has_amd_gpu: bool
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
            else:
                # If neither gpu.vendor nor gpu.name is set, assume Nvidia.
                vendor = gpuhunt.AcceleratorVendor.NVIDIA
                has_amd_gpu = False
            gpu_spec.vendor = vendor
        else:
            has_amd_gpu = vendor == gpuhunt.AcceleratorVendor.AMD
        if has_amd_gpu and conf.image is None:
            raise ConfigurationError("`image` is required if `resources.gpu.vendor` is AMD.")


class RunWithPortsConfigurator(BaseRunConfigurator):
    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        super().register_args(parser)
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

    def apply_args(
        self, conf: BaseRunConfigurationWithPorts, args: argparse.Namespace, unknown: List[str]
    ):
        super().apply_args(conf, args, unknown)
        if args.ports:
            conf.ports = list(merge_ports(conf.ports, args.ports).values())


class TaskConfigurator(RunWithPortsConfigurator):
    TYPE = ApplyConfigurationType.TASK

    def apply_args(self, conf: TaskConfiguration, args: argparse.Namespace, unknown: List[str]):
        super().apply_args(conf, args, unknown)
        self.interpolate_run_args(conf.commands, unknown)


class DevEnvironmentConfigurator(RunWithPortsConfigurator):
    TYPE = ApplyConfigurationType.DEV_ENVIRONMENT

    def apply_args(
        self, conf: DevEnvironmentConfiguration, args: argparse.Namespace, unknown: List[str]
    ):
        super().apply_args(conf, args, unknown)
        if conf.ide == "vscode" and conf.version is None:
            conf.version = _detect_vscode_version()
            if conf.version is None:
                console.print(
                    "[secondary]Unable to detect the VS Code version and pre-install extensions. "
                    "Fix by opening [code]Command Palette[/code], executing [code]Shell Command: "
                    "Install 'code' command in PATH[/code], and restarting terminal.[/]\n"
                )


class ServiceConfigurator(BaseRunConfigurator):
    TYPE = ApplyConfigurationType.SERVICE

    def apply_args(self, conf: ServiceConfiguration, args: argparse.Namespace, unknown: List[str]):
        super().apply_args(conf, args, unknown)
        self.interpolate_run_args(conf.commands, unknown)


def merge_ports(conf: List[PortMapping], args: List[PortMapping]) -> Dict[int, PortMapping]:
    unique_ports_constraint([pm.container_port for pm in conf])
    unique_ports_constraint([pm.container_port for pm in args])
    ports = {pm.container_port: pm for pm in conf}
    for pm in args:  # override conf
        ports[pm.container_port] = pm
    unique_ports_constraint([pm.local_port for pm in ports.values() if pm.local_port is not None])
    return ports


def unique_ports_constraint(ports: List[int]):
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


def _print_service_urls(run: Run) -> None:
    if run._run.run_spec.configuration.type != RunConfigurationType.SERVICE.value:
        return
    console.print(f"Service is published at:\n  [link={run.service_url}]{run.service_url}[/]")
    if model := run.service_model:
        console.print(
            f"Model [code]{model.name}[/] is published at:\n  [link={model.url}]{model.url}[/]"
        )
    console.print()


def _print_finished_message(run: Run):
    if run.status == RunStatus.DONE:
        console.print("[code]Done[/]")
        return

    termination_reason, termination_reason_message = _get_run_termination_reason(run)
    message = "Run failed due to unknown reason. Check CLI, server, and run logs."
    if run.status == RunStatus.TERMINATED:
        message = "Run terminated due to unknown reason. Check CLI, server, and run logs."

    if termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY:
        message = (
            "All provisioning attempts failed. "
            "This is likely due to cloud providers not having enough capacity. "
            "Check CLI and server logs for more details."
        )
    elif termination_reason is not None:
        error_details = (
            f"Error: {termination_reason_message}\n" if termination_reason_message else ""
        )
        message = (
            f"Run failed with error code {termination_reason.name}.\n"
            f"{error_details}"
            "Check CLI, server, and run logs for more details."
        )
    console.print(f"[error]{message}[/]")


def _get_run_exit_code(run: Run) -> int:
    if run.status == RunStatus.DONE:
        return 0
    return 1


def _get_run_termination_reason(run: Run) -> Tuple[Optional[JobTerminationReason], Optional[str]]:
    if len(run._run.jobs) == 0:
        return None, None
    job = run._run.jobs[0]
    if len(job.job_submissions) == 0:
        return None, None
    job_submission = job.job_submissions[0]
    return job_submission.termination_reason, job_submission.termination_reason_message


def _run_resubmitted(run: Run, current_job_submission: Optional[JobSubmission]) -> bool:
    if current_job_submission is None or run._run.latest_job_submission is None:
        return False
    return run.status == RunStatus.PENDING or (
        not run.status.is_finished()
        and run._run.latest_job_submission.submitted_at > current_job_submission.submitted_at
    )
