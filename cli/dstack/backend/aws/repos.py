import json
from typing import List, Optional

from botocore.client import BaseClient

from dstack.backend.aws import runners
from dstack.backend.aws.utils import retry_operation_on_service_errors
from dstack.backend import RepoHead
from dstack.core.repo import RepoCredentials, RepoProtocol, RepoAddress


def list_repo_heads(s3_client: BaseClient, bucket_name: str) -> List[RepoHead]:
    tag_head_prefix = f"repos/l;"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=tag_head_prefix)
    repo_heads = []
    if "Contents" in response:
        for obj in response["Contents"]:
            tokens = obj["Key"][len(tag_head_prefix) :].split(";")
            if len(tokens) == 5:
                (
                    repo_host_port,
                    repo_user_name,
                    repo_name,
                    last_run_at,
                    tags_count,
                ) = tuple(tokens)
                t = repo_host_port.split(":")
                repo_host_name = t[0]
                repo_port = t[1] if len(t) > 1 else None
                repo_heads.append(
                    RepoHead(
                        RepoAddress(repo_host_name, repo_port, repo_user_name, repo_name),
                        int(last_run_at) if last_run_at else None,
                        int(tags_count),
                    )
                )
    return repo_heads


def _get_repo_head(
    s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress
) -> Optional[RepoHead]:
    repo_head_prefix = f"repos/l;{repo_address.path(delimiter=',')};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=repo_head_prefix)
    if response.get("Contents"):
        last_run_at, tags_count = tuple(
            response["Contents"][0]["Key"][len(repo_head_prefix) :].split(";")
        )
        return RepoHead(repo_address, int(last_run_at) if last_run_at else None, int(tags_count))
    else:
        return None


def _create_or_update_repo_head(s3_client: BaseClient, bucket_name: str, repo_head: RepoHead):
    repo_head_prefix = f"repos/l;{repo_head.path(delimiter=',')};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=repo_head_prefix)
    if "Contents" in response:
        for obj in response["Contents"]:
            s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
    repo_head_key = (
        f"{repo_head_prefix}" f"{repo_head.last_run_at or ''};" f"{repo_head.tags_count}"
    )
    s3_client.put_object(Body="", Bucket=bucket_name, Key=repo_head_key)


def update_repo_last_run_at(
    s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress, last_run_at: int
):
    repo_head = _get_repo_head(s3_client, bucket_name, repo_address) or RepoHead(
        repo_address, None, tags_count=0
    )
    repo_head.last_run_at = last_run_at
    _create_or_update_repo_head(s3_client, bucket_name, repo_head)


def increment_repo_tags_count(s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress):
    repo_head = _get_repo_head(s3_client, bucket_name, repo_address) or RepoHead(
        repo_address, None, tags_count=0
    )
    repo_head.tags_count = repo_head.tags_count + 1
    _create_or_update_repo_head(s3_client, bucket_name, repo_head)


def decrement_repo_tags_count(s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress):
    repo_head = _get_repo_head(s3_client, bucket_name, repo_address)
    if repo_head:
        repo_head.tags_count = repo_head.tags_count - 1
        _create_or_update_repo_head(s3_client, bucket_name, repo_head)
    else:
        raise Exception(f"No repo head is found: {repo_address.path()}")


def delete_repo(s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress):
    repo_head_prefix = f"repos/l;{repo_address.path(delimiter=',')};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=repo_head_prefix)
    if "Contents" in response:
        for obj in response["Contents"]:
            s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])


def get_repo_credentials(
    secretsmanager_client: BaseClient, bucket_name: str, repo_address: RepoAddress
) -> Optional[RepoCredentials]:
    secret_name = f"/dstack/{bucket_name}/credentials/{repo_address.path()}"
    try:
        response = secretsmanager_client.get_secret_value(SecretId=secret_name)
        credentials_data = json.loads(response["SecretString"])
        return RepoCredentials(
            RepoProtocol(credentials_data["protocol"]),
            credentials_data.get("private_key"),
            credentials_data.get("oauth_token"),
        )
    except Exception as e:
        if (
            hasattr(e, "response")
            and e.response.get("Error")
            and e.response["Error"].get("Code") == "ResourceNotFoundException"
        ):
            return None


def save_repo_credentials(
    sts_client: BaseClient,
    iam_client: BaseClient,
    secretsmanager_client: BaseClient,
    bucket_name: str,
    repo_address: RepoAddress,
    repo_credentials: RepoCredentials,
):
    secret_name = f"/dstack/{bucket_name}/credentials/{repo_address.path()}"
    credentials_data = {"protocol": repo_credentials.protocol.value}
    if repo_credentials.protocol == RepoProtocol.HTTPS and repo_credentials.oauth_token:
        credentials_data["oauth_token"] = repo_credentials.oauth_token
    elif repo_credentials.protocol == RepoProtocol.SSH:
        if repo_credentials.private_key:
            credentials_data["private_key"] = repo_credentials.private_key
        else:
            raise Exception("No private key is specified")
    try:
        secretsmanager_client.get_secret_value(SecretId=secret_name)
        secretsmanager_client.update_secret(
            SecretId=secret_name, SecretString=json.dumps(credentials_data)
        )
    except Exception as e:
        if (
            hasattr(e, "response")
            and e.response.get("Error")
            and e.response["Error"].get("Code") == "ResourceNotFoundException"
        ):
            secretsmanager_client.create_secret(
                Name=secret_name,
                SecretString=json.dumps(credentials_data),
                Description="Generated by dstack",
                Tags=[
                    {"Key": "owner", "Value": "dstack"},
                    {"Key": "dstack_bucket", "Value": bucket_name},
                ],
            )
        else:
            raise e
    role_name = runners.role_name(iam_client, bucket_name)
    account_id = sts_client.get_caller_identity()["Account"]
    resource_policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{account_id}:role/{role_name}"},
                    "Action": [
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:ListSecrets",
                    ],
                    "Resource": "*",
                }
            ],
        }
    )
    # The policy may not exist yet if we just created it because of AWS eventual consistency
    retry_operation_on_service_errors(
        secretsmanager_client.put_resource_policy,
        ["MalformedPolicyDocumentException"],
        delay=5,
        SecretId=secret_name,
        ResourcePolicy=resource_policy,
    )
