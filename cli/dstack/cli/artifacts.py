import hashlib
import json
import os
import sys
import typing
from argparse import Namespace
from pathlib import Path

import colorama
import requests
from boto3.s3 import transfer
from git import InvalidGitRepositoryError
from tabulate import tabulate
from tqdm import tqdm

from dstack.cli.common import get_user_info, boto3_client, list_artifact, short_artifact_path, list_artifact_files, \
    get_jobs, load_repo_data
from dstack.config import get_config, ConfigurationError


def download_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        user_info = get_user_info(profile)

        jobs = get_jobs(args.run_name, profile)
        if args.workflow_name is not None:
            jobs = list(filter(lambda j: j["workflow_name"] == args.workflow_name, jobs))

        for job in jobs:
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

        jobs = get_jobs(args.run_name, profile)
        if args.workflow_name is not None:
            jobs = list(filter(lambda j: j["workflow_name"] == args.workflow_name, jobs))

        for job in jobs:
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
                        artifact_name = short_artifact_path(artifact_path)
                        header_added = False
                        for i in range(len(files)):
                            file, size = files[i]
                            if (len(file) > 0 and not file.endswith('/')) or size > 0:
                                table_rows.append([
                                    artifact_name if not header_added else "",
                                    file,
                                    sizeof_fmt(size)
                                ])
                                header_added = True
                    print(tabulate(table_rows, headers=table_headers, tablefmt="plain"))

    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def submit_run_and_job(profile, workflow_name: str, artifacts: typing.List[str],
                       tag_name: typing.Optional[str] = None):
    repo_url, repo_branch, repo_hash, repo_diff = load_repo_data()

    headers = {
        "Content-Type": f"application/json; charset=utf-8"
    }
    if profile.token is not None:
        headers["Authorization"] = f"Bearer {profile.token}"

    data = {
        "workflow_name": workflow_name,
        "repo_url": repo_url,
        "repo_branch": repo_branch,
        "repo_hash": repo_hash,
        "status": "done",
        "tag_name": tag_name,
    }
    if repo_diff:
        data["repo_diff"] = repo_diff
    data_bytes = json.dumps(data).encode("utf-8")
    response = requests.request(method="POST", url=f"{profile.server}/runs/submit",
                                data=data_bytes,
                                headers=headers, verify=profile.verify)
    run_name = ""
    if response.status_code == 200:
        run_name = response.json().get("run_name")
    elif response.status_code == 404 and response.json().get("message") == "repo not found":
        sys.exit("Call 'dstack init' first")
    else:
        response.raise_for_status()

    data["run_name"] = run_name
    # TODO: Hardcode
    data["image_name"] = "python:3.9"
    data["artifacts"] = artifacts

    data_bytes = json.dumps(data).encode("utf-8")
    response = requests.request(method="POST", url=f"{profile.server}/jobs/submit",
                                data=data_bytes,
                                headers=headers, verify=profile.verify)
    job_id = ""
    if response.status_code == 200:
        job_id = response.json().get("job_id")
    elif response.status_code == 404 and response.json().get("message") == "repo not found":
        sys.exit("Call 'dstack init' first")
    else:
        response.raise_for_status()

    return run_name, job_id


def upload_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        user_info = get_user_info(profile)

        local_paths = []
        artifacts = []
        for local_dir in args.local_dirs:
            path = Path(local_dir)
            if path.is_dir():
                local_paths.append(path)
                artifacts.append(path.name)
            else:
                exit(f"The '{local_dir}' path doesn't refer to an existing directory")

        run_name, job_id = submit_run_and_job(profile, args.workflow_name or "upload",
                                              artifacts, tag_name=args.tag_name)

        artifacts_s3_bucket = user_info["user_configuration"]["artifacts_s3_bucket"] if user_info.get(
            "user_configuration") is not None and user_info["user_configuration"].get(
            "artifacts_s3_bucket") is not None else user_info["default_configuration"]["artifacts_s3_bucket"]

        for local_path in local_paths:
            # TODO: Hardcode
            artifact_path = f"{user_info['user_name']}/{run_name}/{job_id}/{local_path.name}"
            upload_artifact(boto3_client(user_info, "s3"), artifacts_s3_bucket, artifact_path,
                            local_dir=local_path.absolute())
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def __remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text


def upload_artifact(client, artifacts_s3_bucket, artifact_path, local_dir):
    total_size = 0
    for root, sub_dirs, files in os.walk(local_dir):
        for filename in files:
            file_path = os.path.join(root, filename)
            file_size = os.path.getsize(file_path)
            total_size += file_size

    uploader = transfer.S3Transfer(client, transfer.TransferConfig(), transfer.OSUtils())

    with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024,
              desc=f"Uploading artifact '{short_artifact_path(artifact_path)}'") as pbar:
        def callback(size):
            pbar.update(size)

        for root, sub_dirs, files in os.walk(local_dir):
            for filename in files:
                file_path = os.path.join(root, filename)

                key = artifact_path + __remove_prefix(str(file_path), str(Path(local_dir).absolute()))
                uploader.upload_file(
                    str(file_path),
                    artifacts_s3_bucket,
                    key,
                    callback=callback,
                )


def download_artifact(client, artifacts_s3_bucket, artifact_path, output_dir=None):
    output_path = Path(output_dir if output_dir is not None else os.getcwd())

    response = client.list_objects(Bucket=artifacts_s3_bucket, Prefix=artifact_path)

    total_size = 0
    keys = []
    etags = []
    for obj in response.get("Contents") or []:
        key = obj["Key"]
        etag = obj["ETag"]
        dest_path = dest_file_path(key, output_path)
        if dest_path.exists():
            etag_path = etag_file_path(key, output_path)
            if etag_path.exists():
                if etag_path.read_text() != etag:
                    os.remove(etag_path)
                    os.remove(dest_path)
                else:
                    continue

        total_size += obj["Size"]
        if obj["Size"] > 0 and not key.endswith("/"):
            # Skip empty files that designate folders (required by FUSE)
            keys.append(key)
            etags.append(etag)

    downloader = transfer.S3Transfer(client, transfer.TransferConfig(), transfer.OSUtils())

    # TODO: Make download files in parallel
    with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024,
              desc=f"Downloading artifact '{short_artifact_path(artifact_path)}'") as pbar:
        for i in range(len(keys)):
            key = keys[i]
            etag = etags[i]

            def callback(size):
                pbar.update(size)

            file_path = dest_file_path(key, output_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            downloader.download_file(artifacts_s3_bucket, key, str(file_path), callback=callback)

            etag_path = Path(etag_file_path(key, output_path))
            etag_path.parent.mkdir(parents=True, exist_ok=True)
            etag_path.write_text(etag)


def dest_file_path(key, output_path):
    return output_path / Path(short_artifact_path(key))


def etag_file_path(key, output_path):
    return cache_dir() / Path(str(hashlib.md5(str(Path(output_path).absolute()).encode('utf-8')).hexdigest())) / Path(
        key + ".etag")


def cache_dir():
    return Path.home() / Path(".dstack/.cache")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("artifacts", help="List, download, or upload artifacts")
    subparsers = parser.add_subparsers()
    upload_parser = subparsers.add_parser("upload", help="Upload artifacts", )
    upload_parser.add_argument("local_dirs", metavar="LOCAL_DIR", type=str, nargs="+")
    upload_parser.add_argument("--workflow", "-w", help="The name of the workflow", type=str, nargs="?",
                               dest="workflow_name")
    upload_parser.add_argument("--tag", "-t", help="The tag name to assign to the generated run", type=str, nargs="?",
                               dest="tag_name")
    upload_parser.set_defaults(func=upload_func)

    list_parser = subparsers.add_parser("list", help="Download artifacts", )
    list_parser.add_argument("run_name", metavar="RUN", type=str)
    list_parser.add_argument("workflow_name", metavar="WORKFLOW", type=str, nargs="?")
    parser.add_argument("--total", "-t", help="Show only the total sizes of artifacts", action="store_true")
    list_parser.set_defaults(func=list_func)

    download_parser = subparsers.add_parser("download", help="Download artifacts", )
    download_parser.add_argument("run_name", metavar="RUN", type=str)
    download_parser.add_argument("workflow_name", metavar="WORKFLOW", type=str, nargs="?")
    download_parser.add_argument("--output", "-o", help="The directory to download artifacts to. "
                                                        "By default, it's the current directory.", type=str, nargs="?")
    download_parser.set_defaults(func=download_func)
