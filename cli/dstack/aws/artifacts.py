import os
from pathlib import Path
from typing import List, Tuple, Optional, Generator

from boto3.s3 import transfer
from botocore.client import BaseClient
from tqdm import tqdm


def dest_file_path(key: str, output_path: Path) -> Path:
    return output_path / "/".join(key.split("/")[4:])


def download_run_artifact_files(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str,
                                run_name: str, output_dir: Optional[str]):
    artifact_prefix = f"artifacts/{repo_user_name}/{repo_name}/{run_name},"

    output_path = Path(output_dir or os.getcwd())

    total_size = 0
    keys = []
    paginator = s3_client.get_paginator('list_objects')
    page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=artifact_prefix)
    for page in page_iterator:
        for obj in (page.get("Contents") or []):
            key = obj["Key"]

            total_size += obj["Size"]
            if obj["Size"] > 0 and not key.endswith("/"):
                keys.append(key)

    downloader = transfer.S3Transfer(s3_client, transfer.TransferConfig(), transfer.OSUtils())

    # TODO: Make download files in parallel
    with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024,
              desc=f"Downloading artifacts") as pbar:
        def callback(size):
            pbar.update(size)

        for i in range(len(keys)):
            key = keys[i]

            file_path = dest_file_path(key, output_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            downloader.download_file(bucket_name, key, str(file_path), callback=callback)


def list_run_artifact_files(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str,
                            run_name: str) -> Generator[Tuple[str, str, int], None, None]:
    artifact_prefix = f"artifacts/{repo_user_name}/{repo_name}/{run_name},"
    paginator = s3_client.get_paginator('list_objects')
    page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=artifact_prefix)
    for page in page_iterator:
        for obj in (page.get("Contents") or []):
            if obj["Size"] > 0:
                yield obj["Key"].split("/")[4], "/".join(obj["Key"].split("/")[5:]), obj["Size"]


def __remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text


def upload_job_artifact_files(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str, job_id: str,
                              artifact_name: str, local_path: Path):
    total_size = 0
    for root, sub_dirs, files in os.walk(local_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            file_size = os.path.getsize(file_path)
            total_size += file_size

    uploader = transfer.S3Transfer(s3_client, transfer.TransferConfig(), transfer.OSUtils())

    with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024,
              desc=f"Uploading artifact '{artifact_name}'") as pbar:
        def callback(size):
            pbar.update(size)

        prefix = f"artifacts/{repo_user_name}/{repo_name}/{job_id}/{artifact_name}"
        for root, sub_dirs, files in os.walk(local_path):
            for filename in files:
                file_path = Path(os.path.join(root, filename)).absolute()

                key = prefix + __remove_prefix(str(file_path), str(local_path.absolute()))
                uploader.upload_file(
                    str(file_path),
                    bucket_name,
                    key,
                    callback=callback,
                )


def list_run_artifact_files_and_folders(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str,
                                        job_id: str, path: str) -> List[Tuple[str, bool]]:
    prefix = f"artifacts/{repo_user_name}/{repo_name}/{job_id}/" + path + ("" if path.endswith("/") else "/")
    response = s3_client.list_objects(Bucket=bucket_name, Prefix=prefix, Delimiter="/")
    folders = []
    files = []
    if "CommonPrefixes" in response:
        for f in response["CommonPrefixes"]:
            folder_name = f["Prefix"][len(prefix):]
            if folder_name.endswith("/"):
                folder_name = folder_name[:-1]
            folders.append(folder_name)
    if "Contents" in response:
        for f in response["Contents"]:
            files.append(f["Key"][len(prefix):])
    return [(folder, True) for folder in folders] + [(file, False) for file in files]
