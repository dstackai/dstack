import hashlib
import os
from pathlib import Path
from typing import Optional, List, Tuple

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


def download_job_artifact_files(client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str, job_id: str,
                                artifact_name: str, output_dir: str):
    output_path = Path(output_dir)

    artifact_prefix = f"artifacts/{repo_user_name}/{repo_name}/{job_id}/{artifact_name}"
    response = client.list_objects(Bucket=bucket_name, Prefix=artifact_prefix)

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
              desc=f"Downloading '{artifact_name}'") as pbar:
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


def list_job_artifact_files(client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str, job_id: str,
                            artifact_name: str, ) -> List[Tuple[str, int]]:
    artifact_prefix = f"artifacts/{repo_user_name}/{repo_name}/{job_id}/{artifact_name}"
    response = client.list_objects(Bucket=bucket_name, Prefix=artifact_prefix)

    return [("/".join(obj["Key"].split("/")[4:]), obj["Size"]) for obj in
            (response.get("Contents") or []) if obj["Size"] > 0]
