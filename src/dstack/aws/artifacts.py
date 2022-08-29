import hashlib
import os
from pathlib import Path
from typing import List, Tuple, Optional

from boto3.s3 import transfer
from botocore.client import BaseClient
from tqdm import tqdm


def cache_dir():
    return Path.home() / Path(".dstack/.cache")


def etag_file_path(key, output_path):
    return cache_dir() / Path(str(hashlib.md5(str(Path(output_path).absolute()).encode('utf-8')).hexdigest())) / Path(
        key + ".etag")


def dest_file_path(key: str, output_path: Path) -> Path:
    return output_path / "/".join(key.split("/")[4:])


def download_run_artifact_files(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str,
                                run_name: str, output_dir: Optional[str]):
    artifact_prefix = f"artifacts/{repo_user_name}/{repo_name}/{run_name},"
    response = s3_client.list_objects(Bucket=bucket_name, Prefix=artifact_prefix)

    output_path = Path(output_dir or os.getcwd())

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
            keys.append(key)
            etags.append(etag)

    downloader = transfer.S3Transfer(s3_client, transfer.TransferConfig(), transfer.OSUtils())

    # TODO: Make download files in parallel
    with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024,
              desc=f"Downloading artifacts") as pbar:
        for i in range(len(keys)):
            key = keys[i]
            etag = etags[i]

            def callback(size):
                pbar.update(size)

            file_path = dest_file_path(key, output_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            downloader.download_file(bucket_name, key, str(file_path), callback=callback)

            etag_path = Path(etag_file_path(key, output_path))
            etag_path.parent.mkdir(parents=True, exist_ok=True)
            etag_path.write_text(etag)


def list_run_artifact_files(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str,
                            run_name: str) -> List[Tuple[str, str, int]]:
    artifact_prefix = f"artifacts/{repo_user_name}/{repo_name}/{run_name},"
    response = s3_client.list_objects(Bucket=bucket_name, Prefix=artifact_prefix)

    return [(obj["Key"].split("/")[4], "/".join(obj["Key"].split("/")[5:]), obj["Size"]) for obj in
            (response.get("Contents") or []) if obj["Size"] > 0]


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
