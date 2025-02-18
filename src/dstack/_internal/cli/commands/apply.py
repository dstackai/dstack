import argparse
from pathlib import Path

from argcomplete import FilesCompleter

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators import (
    get_apply_configurator_class,
    load_apply_configuration,
)
from dstack._internal.cli.services.repos import (
    init_default_virtual_repo,
    init_repo,
    register_init_repo_args,
)
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import ApplyConfigurationType

NOTSET = object()


class ApplyCommand(APIBaseCommand):
    NAME = "apply"
    DESCRIPTION = "Apply a configuration"
    DEFAULT_HELP = False

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "-h",
            "--help",
            nargs="?",
            type=ApplyConfigurationType,
            default=NOTSET,
            help="Show this help message and exit.",
            dest="help",
            metavar="TYPE",
        )
        self._parser.add_argument(
            "-f",
            "--file",
            type=Path,
            metavar="FILE",
            help="The path to the configuration file. Defaults to [code]$PWD/.dstack.yml[/]",
            dest="configuration_file",
        ).completer = FilesCompleter(allowednames=["*.yml", "*.yaml"])
        self._parser.add_argument(
            "-y",
            "--yes",
            help="Do not ask for confirmation",
            action="store_true",
        )
        self._parser.add_argument(
            "--force",
            help="Force apply when no changes detected",
            action="store_true",
        )
        self._parser.add_argument(
            "-d",
            "--detach",
            help="Exit immediately after submitting configuration",
            action="store_true",
        )
        repo_group = self._parser.add_argument_group("Repo Options")
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

    def _command(self, args: argparse.Namespace):
        try:
            if args.help is not NOTSET:
                if args.help is not None:
                    configurator_class = get_apply_configurator_class(
                        ApplyConfigurationType(args.help)
                    )
                    configurator_class.register_args(self._parser)
                    self._parser.print_help()
                    return
                self._parser.print_help()
                console.print(
                    "\nType `dstack apply -h CONFIGURATION_TYPE` to see configuration-specific options.\n"
                )
                return

            super()._command(args)
            if args.repo and args.no_repo:
                raise CLIError("Either --repo or --no-repo can be specified")
            repo = None
            if args.repo:
                repo = init_repo(
                    api=self.api,
                    repo_path=args.repo,
                    repo_branch=args.repo_branch,
                    repo_hash=args.repo_hash,
                    local=args.local,
                    git_identity_file=args.git_identity_file,
                    oauth_token=args.gh_token,
                    ssh_identity_file=args.ssh_identity_file,
                )
            elif args.no_repo:
                repo = init_default_virtual_repo(api=self.api)
            configuration_path, configuration = load_apply_configuration(args.configuration_file)
            configurator_class = get_apply_configurator_class(configuration.type)
            configurator = configurator_class(api_client=self.api)
            configurator_parser = configurator.get_parser()
            known, unknown = configurator_parser.parse_known_args(args.unknown)
            configurator.apply_configuration(
                conf=configuration,
                configuration_path=configuration_path,
                command_args=args,
                configurator_args=known,
                unknown_args=unknown,
                repo=repo,
            )
        except KeyboardInterrupt:
            console.print("\nOperation interrupted by user. Exiting...")
            exit(0)
