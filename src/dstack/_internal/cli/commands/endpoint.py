import argparse
import shlex
from typing import cast

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators.run import ServiceConfigurator
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.harness import (
    EndpointCreateParams,
    deploy_service_configuration,
    deploy_service_with_self_healing,
)
from dstack._internal.harness.generator import (
    generate_service_configuration,
    save_service_configuration,
)


class EndpointCommand(APIBaseCommand):
    NAME = "endpoint"
    DESCRIPTION = "Manage inference endpoints"
    ACCEPT_EXTRA_ARGS = True

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._print_help)
        subparsers = self._parser.add_subparsers(dest="action")

        create_parser = subparsers.add_parser(
            "create",
            help="Create an inference endpoint",
            formatter_class=self._parser.formatter_class,
        )
        create_parser.add_argument(
            "--model",
            required=True,
            metavar="NAME",
            help="The model to deploy",
        )
        create_parser.add_argument(
            "--skill-path",
            metavar="PATH",
            help="Path to [code]skills/dstack/SKILL.md[/]. Defaults to project skill file",
        )
        create_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Generate and save the configuration without deploying",
        )
        create_parser.add_argument(
            "-y",
            "--yes",
            help="Do not ask for confirmation",
            action="store_true",
        )
        create_parser.add_argument(
            "-d",
            "--detach",
            help="Exit immediately after submitting instead of streaming container logs",
            action="store_true",
        )
        create_parser.add_argument(
            "-v",
            "--verbose",
            help="Show all plan properties including those with default values",
            action="store_true",
        )
        create_parser.add_argument(
            "--force",
            help="Force apply when no changes detected",
            action="store_true",
        )
        create_parser.add_argument(
            "--max-attempts",
            type=int,
            default=3,
            metavar="N",
            help=(
                "Max deploy attempts. On container failure, the harness stops the run,"
                " asks the model to fix the configuration from the error logs, and redeploys."
                " Set to 1 to disable self-healing"
            ),
        )
        ServiceConfigurator.register_args(create_parser)
        create_parser.set_defaults(subfunc=self._create)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _print_help(self, args: argparse.Namespace):
        self._parser.print_help()

    def _create(self, args: argparse.Namespace):
        configurator_parser = ServiceConfigurator.get_parser()
        _, unknown_args = configurator_parser.parse_known_args(args.extra_args)
        if unknown_args:
            raise CLIError(f"Unrecognized arguments: {shlex.join(unknown_args)}")

        params = EndpointCreateParams.from_namespace(args, model=args.model)

        with console.status("Generating service configuration..."):
            configuration = generate_service_configuration(
                params=params,
                skill_path=args.skill_path,
            )

        configurator = ServiceConfigurator(api_client=self.api)
        configurator.apply_args(cast(TaskConfiguration, configuration), args)
        configuration.model = args.model

        config_path = save_service_configuration(configuration)
        console.print(f"Saved configuration to [code]{config_path}[/]")

        if args.dry_run:
            console.print("Dry run complete. Skipping deployment.")
            return

        apply_args = argparse.Namespace(
            yes=args.yes,
            detach=args.detach,
            verbose=args.verbose,
            force=args.force,
        )

        if args.detach:
            deploy_service_configuration(
                api=self.api,
                configuration=configuration,
                configuration_path=config_path,
                command_args=apply_args,
                configurator_args=args,
            )
            return

        deploy_service_with_self_healing(
            api=self.api,
            configuration=configuration,
            params=params,
            configuration_path=config_path,
            command_args=apply_args,
            configurator_args=args,
            skill_path=args.skill_path,
            max_attempts=args.max_attempts,
        )
