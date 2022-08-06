import os
import os
import sys
from argparse import Namespace

from git import InvalidGitRepositoryError
from rich.console import Console
from rich.table import Table

from dstack.backend import load_backend
from dstack.cli.common import load_repo_data
from dstack.config import ConfigError


def download_func(args: Namespace):
    try:
        backend = load_backend()
        repo_user_name, repo_name, _, _, _ = load_repo_data()
        backend.download_run_artifact_files(repo_user_name, repo_name, args.run_name, args.output)
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def list_func(args: Namespace):
    try:
        backend = load_backend()
        repo_user_name, repo_name, _, _, _ = load_repo_data()
        run_artifact_files = backend.list_run_artifact_files(repo_user_name, repo_name, args.run_name)
        console = Console()
        table = Table()
        table.add_column("Artifact")
        table.add_column("File")
        table.add_column("Size")
        previous_artifact_name = None
        for (artifact_name, file_name, file_size) in run_artifact_files:
            table.add_row(artifact_name if previous_artifact_name != artifact_name else "",
                          file_name, sizeof_fmt(file_size))
            previous_artifact_name = artifact_name
        console.print(table)
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


# def upload_func(args: Namespace):
#     try:
#         dstack_config = get_config()
#         # TODO: Support non-default profiles
#         profile = dstack_config.get_profile("default")
#         user_info = get_user_info(profile)
#
#         local_paths = []
#         artifacts = []
#         for local_dir in args.local_dirs:
#             path = Path(local_dir)
#             if path.is_dir():
#                 local_paths.append(path)
#                 artifacts.append(path.name)
#             else:
#                 exit(f"The '{local_dir}' path doesn't refer to an existing directory")
#
#         run_name, job_id = submit_run_and_job(profile, None,
#                                               artifacts, tag_name=args.tag_name)
#
#         artifacts_s3_bucket = user_info["user_configuration"]["artifacts_s3_bucket"] if user_info.get(
#             "user_configuration") is not None and user_info["user_configuration"].get(
#             "artifacts_s3_bucket") is not None else user_info["default_configuration"]["artifacts_s3_bucket"]
#
#         for local_path in local_paths:
#             # TODO: Hardcode
#             artifact_path = f"{user_info['user_name']}/{run_name}/{job_id}/{local_path.name}"
#             upload_artifact(boto3_client(user_info, "s3"), artifacts_s3_bucket, artifact_path,
#                             local_dir=local_path.absolute())
#     except InvalidGitRepositoryError:
#         sys.exit(f"{os.getcwd()} is not a Git repo")
#     except ConfigurationError:
#         sys.exit(f"Call 'dstack config' first")


# def __remove_prefix(text, prefix):
#     if text.startswith(prefix):
#         return text[len(prefix):]
#     return text


# def upload_artifact(client, artifacts_s3_bucket, artifact_path, local_dir):
#     total_size = 0
#     for root, sub_dirs, files in os.walk(local_dir):
#         for filename in files:
#             file_path = os.path.join(root, filename)
#             file_size = os.path.getsize(file_path)
#             total_size += file_size
#
#     uploader = transfer.S3Transfer(client, transfer.TransferConfig(), transfer.OSUtils())
#
#     with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024,
#               desc=f"Uploading artifact '{short_artifact_path(artifact_path)}'") as pbar:
#         def callback(size):
#             pbar.update(size)
#
#         for root, sub_dirs, files in os.walk(local_dir):
#             for filename in files:
#                 file_path = os.path.join(root, filename)
#
#                 key = artifact_path + __remove_prefix(str(file_path), str(Path(local_dir).absolute()))
#                 uploader.upload_file(
#                     str(file_path),
#                     artifacts_s3_bucket,
#                     key,
#                     callback=callback,
#                 )


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("artifacts", help="List, download, or upload artifacts")
    subparsers = parser.add_subparsers()
    # upload_parser = subparsers.add_parser("upload", help="Upload artifacts", )
    # upload_parser.add_argument("local_dirs", metavar="LOCAL_DIR", type=str, nargs="+")
    # upload_parser.add_argument("--tag", "-t", help="The tag name to assign to the generated run", type=str,
    #                            dest="tag_name")
    # upload_parser.set_defaults(func=upload_func)

    list_parser = subparsers.add_parser("list", help="Download artifacts", )
    list_parser.add_argument("run_name", metavar="RUN", type=str, help="A name of a run")
    # list_parser.add_argument("workflow_name", metavar="WORKFLOW", type=str, nargs="?", help="A name of a workflow")
    # parser.add_argument("--total", "-t", help="Show only the total sizes of artifacts", action="store_true")
    list_parser.set_defaults(func=list_func)

    download_parser = subparsers.add_parser("download", help="Download artifacts", )
    download_parser.add_argument("run_name", metavar="RUN", type=str, help="A name of a run")
    # download_parser.add_argument("workflow_name", metavar="WORKFLOW", type=str, nargs="?", help="A name of a workflow")
    download_parser.add_argument("--output", "-o", help="The directory to download artifacts to. "
                                                        "By default, it's the current directory.", type=str)
    download_parser.set_defaults(func=download_func)
