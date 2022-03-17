import os
import sys
from argparse import Namespace

import colorama
from git import InvalidGitRepositoryError
from tabulate import tabulate

from dstack.cli.common import get_job, get_user_info, boto3_client, download_artifact, list_artifact, \
    short_artifact_path, list_artifact_files
from dstack.config import get_config, ConfigurationError


def download_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        user_info = get_user_info(profile)

        job = get_job(args.job_id, profile)

        if job is not None:
            artifacts_s3_bucket = job["user_artifacts_s3_bucket"] if user_info.get(
                "user_configuration") is not None and job.get(
                "user_artifacts_s3_bucket") is not None else user_info["default_configuration"]["artifacts_s3_bucket"]
            artifact_paths = job.get("artifact_paths")
            if artifact_paths is None or len(artifact_paths) == 0:
                print("No artifacts")
            else:
                for artifact_path in artifact_paths:
                    download_artifact(boto3_client(user_info, "s3", job), artifacts_s3_bucket, artifact_path,
                                      args.output)
        else:
            sys.exit(f"Job '{args.job_id}' not found")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


# TODO: Group files by artifacts if '--long' is used
def list_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        user_info = get_user_info(profile)

        job = get_job(args.job_id, profile)

        if job is not None:
            artifacts_s3_bucket = job["user_artifacts_s3_bucket"] if user_info.get(
                "user_configuration") is not None and job.get(
                "user_artifacts_s3_bucket") is not None else user_info["default_configuration"]["artifacts_s3_bucket"]
            artifact_paths = job.get("artifact_paths")
            if artifact_paths is None or len(artifact_paths) == 0:
                print("No artifacts")
            else:
                if args.total is True:
                    table_headers = [
                        f"{colorama.Fore.LIGHTMAGENTA_EX}ARTIFACT{colorama.Fore.RESET}",
                        f"{colorama.Fore.LIGHTMAGENTA_EX}SIZE{colorama.Fore.RESET}",
                        f"{colorama.Fore.LIGHTMAGENTA_EX}FILES{colorama.Fore.RESET}"
                    ]
                    table_rows = []
                    for artifact_path in artifact_paths:
                        keys_total, total_size = list_artifact(boto3_client(user_info, "s3", job),
                                                               artifacts_s3_bucket, artifact_path)
                        table_rows.append([
                            short_artifact_path(artifact_path),
                            sizeof_fmt(total_size),
                            keys_total
                        ])
                    print(tabulate(table_rows, headers=table_headers, tablefmt="plain"))
                else:
                    table_headers = [
                        f"{colorama.Fore.LIGHTMAGENTA_EX}ARTIFACT{colorama.Fore.RESET}",
                        f"{colorama.Fore.LIGHTMAGENTA_EX}FILE{colorama.Fore.RESET}",
                        f"{colorama.Fore.LIGHTMAGENTA_EX}SIZE{colorama.Fore.RESET}"
                    ]
                    table_rows = []
                    for artifact_path in artifact_paths:
                        files = list_artifact_files(boto3_client(user_info, "s3", job),
                                                    artifacts_s3_bucket, artifact_path)
                        for file, size in files:
                            table_rows.append([
                                short_artifact_path(artifact_path),
                                file,
                                sizeof_fmt(size)
                            ])
                    print(tabulate(table_rows, headers=table_headers, tablefmt="plain"))

    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def artifacts_func(args: Namespace):
    if args.output is None:
        list_func(args)
    else:
        download_func(args)


# TODO: Make it work a) with a run name; b) without run name or job id
def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("artifacts", help="Show or download artifacts of a job")
    parser.add_argument('job_id', metavar='JOB', type=str)
    parser.add_argument("--output", "-o", help="The directory to download artifacts to", type=str, nargs="?")
    parser.add_argument("--total", "-t", help="Show only the total sizes of artifacts", action="store_true")
    parser.set_defaults(func=artifacts_func)
