import argparse
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators.run import (
    BaseRunConfigurator,
    run_configurators_mapping,
)
from dstack._internal.cli.services.profile import (
    apply_profile_args,
    register_profile_args,
)
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.run import print_run_plan
from dstack._internal.core.errors import CLIError, ConfigurationError, ServerClientError
from dstack._internal.core.models.configurations import RunConfigurationType
from dstack._internal.core.models.runs import JobSubmission, JobTerminationReason
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.utils.logging import get_logger
from dstack.api import RunStatus
from dstack.api._public.runs import Run
from dstack.api.utils import load_configuration, load_profile

logger = get_logger(__name__)
NOTSET = object()


class RunCommand(APIBaseCommand):
    NAME = "run"
    DESCRIPTION = "Run a configuration"
    DEFAULT_HELP = False

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "-h",
            "--help",
            nargs="?",
            type=RunConfigurationType,
            default=NOTSET,
            help="Show this help message and exit. TYPE is one of [code]task[/], [code]dev-environment[/], [code]service[/]",
            dest="help",
            metavar="TYPE",
        )
        self._parser.add_argument("working_dir")
        self._parser.add_argument(
            "-f",
            "--file",
            type=Path,
            metavar="FILE",
            help="The path to the run configuration file. Defaults to [code]WORKING_DIR/.dstack.yml[/]",
            dest="configuration_file",
        )
        self._parser.add_argument(
            "-n",
            "--name",
            dest="run_name",
            help="The name of the run. If not specified, a random name is assigned",
        )
        self._parser.add_argument(
            "-d",
            "--detach",
            help="Do not poll logs and run status",
            action="store_true",
        )
        self._parser.add_argument(
            "-y",
            "--yes",
            help="Do not ask for plan confirmation",
            action="store_true",
        )
        self._parser.add_argument(
            "--max-offers",
            help="Number of offers to show in the run plan",
            type=int,
            default=3,
        )
        register_profile_args(self._parser)

    def _command(self, args: argparse.Namespace):
        if args.help is not NOTSET:
            if args.help is not None:
                run_configurators_mapping[RunConfigurationType(args.help)].register(self._parser)
            else:
                BaseRunConfigurator.register(self._parser)
            self._parser.print_help()
            return

        super()._command(args)
        try:
            repo = self.api.repos.load(Path.cwd())
            self.api.ssh_identity_file = (
                ConfigManager().get_repo_config(repo.repo_dir).ssh_key_path
            )
            profile = load_profile(Path.cwd(), args.profile)
            configuration_path, conf = load_configuration(
                Path.cwd(), args.working_dir, args.configuration_file
            )
            apply_profile_args(args, conf)
            logger.debug("Configuration loaded: %s", configuration_path)
            parser = argparse.ArgumentParser()
            configurator = run_configurators_mapping[RunConfigurationType(conf.type)]
            configurator.register(parser)
            known, unknown = parser.parse_known_args(args.unknown)
            configurator.apply(known, unknown, conf)

            with console.status("Getting run plan..."):
                run_plan = self.api.runs.get_plan(
                    configuration=conf,
                    repo=repo,
                    configuration_path=configuration_path,
                    backends=profile.backends,
                    regions=profile.regions,
                    instance_types=profile.instance_types,
                    spot_policy=profile.spot_policy,  # pass profile piece by piece
                    retry_policy=profile.retry_policy,
                    max_duration=profile.max_duration,
                    max_price=profile.max_price,
                    working_dir=args.working_dir,
                    run_name=args.run_name,
                    pool_name=profile.pool_name,
                    instance_name=profile.instance_name,
                    creation_policy=profile.creation_policy,
                    termination_policy=profile.termination_policy,
                    termination_policy_idle=profile.termination_idle_time,
                )
        except ConfigurationError as e:
            raise CLIError(str(e))

        print_run_plan(run_plan, offers_limit=args.max_offers)
        if not args.yes and not confirm_ask("Continue?"):
            console.print("\nExiting...")
            return

        if args.run_name:
            old_run = self.api.runs.get(run_name=args.run_name)
            if old_run is not None:
                if not args.yes and not confirm_ask(
                    f"Run [code]{args.run_name}[/] already exists. Override the run?"
                ):
                    console.print("\nExiting...")
                    return

        try:
            with console.status("Submitting run..."):
                run = self.api.runs.exec_plan(run_plan, repo, reserve_ports=not args.detach)
        except ServerClientError as e:
            raise CLIError(e.msg)

        if args.detach:
            console.print(f"Run [code]{run.name}[/] submitted, detaching...")
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
                    if run._run.run_spec.configuration.type == RunConfigurationType.SERVICE.value:
                        console.print(
                            f"Service is published at [link={run.service_url}]{run.service_url}[/]\n"
                        )
                    try:
                        if run.attach():
                            for entry in run.logs():
                                sys.stdout.buffer.write(entry)
                                sys.stdout.buffer.flush()
                        else:
                            console.print("[error]Failed to attach, exiting...[/]")
                            return
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
                        return
                    time.sleep(1)
                if not reattach:
                    console.print(
                        "[error]Lost run connection. Timed out waiting for run final status."
                        " Check `dstack ps` to see if it's done or failed."
                    )
                    return
        except KeyboardInterrupt:
            try:
                if not confirm_ask("\nStop the run before detaching?"):
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


def _print_finished_message(run: Run):
    if run.status == RunStatus.DONE:
        console.print("[code]Done[/]")
        return

    termination_reason, termination_reason_message = _get_run_termination_reason(run)
    message = "Run failed due to unknown reason. Check CLI and server logs."
    if run.status == RunStatus.TERMINATED:
        message = "Run terminated due to unknown reason. Check CLI and server logs."

    if termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY:
        message = (
            "All provisioning attempts failed. "
            "This is likely due to cloud providers not having enough capacity. "
            "Check CLI and server logs for more details."
        )
    elif termination_reason == JobTerminationReason.CREATING_CONTAINER_ERROR:
        message = (
            "Cannot create container.\n"
            f"Error: {termination_reason_message}\n"
            "Check CLI and server logs for more details."
        )
    elif termination_reason == JobTerminationReason.EXECUTOR_ERROR:
        message = (
            f"Error: {termination_reason_message}\nCheck CLI and server logs for more details."
        )
    elif termination_reason is not None:
        message = (
            f"Run failed with error code {termination_reason.name}.\n"
            f"Error: {termination_reason_message}\n"
            "Check CLI and server logs for more details."
        )
    console.print(f"[error]{message}[/]")


def _get_run_termination_reason(run: Run) -> Tuple[Optional[JobTerminationReason], Optional[str]]:
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
