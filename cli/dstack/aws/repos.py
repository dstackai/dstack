import json
from typing import List, Optional

from botocore.client import BaseClient

from dstack.aws import runners
from dstack.backend import RepoHead
from dstack.repo import RepoCredentials, RepoProtocol


def list_repo_heads(s3_client: BaseClient, bucket_name: str) -> List[RepoHead]:
    tag_head_prefix = f"repos/l;"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=tag_head_prefix)
    repo_heads = []
    if "Contents" in response:
        for obj in response["Contents"]:
            repo_user_name, repo_name, last_run_at, tags_count = tuple(obj["Key"][len(tag_head_prefix):].split(';'))
            repo_heads.append(RepoHead(repo_user_name, repo_name, int(last_run_at) if last_run_at else None,
                                       int(tags_count)))
    return repo_heads


def _get_repo_head(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str) -> Optional[RepoHead]:
    repo_head_prefix = f"repos/l;{repo_user_name};{repo_name};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=repo_head_prefix)
    if response.get("Contents"):
        last_run_at, tags_count = tuple(response["Contents"][0]["Key"][len(repo_head_prefix):].split(';'))
        return RepoHead(repo_user_name, repo_name, int(last_run_at) if last_run_at else None,
                        int(tags_count))
    else:
        return None


def _create_or_update_repo_head(s3_client: BaseClient, bucket_name: str, repo_head: RepoHead):
    repo_head_prefix = f"repos/l;{repo_head.repo_user_name};{repo_head.repo_name};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=repo_head_prefix)
    if "Contents" in response:
        for obj in response["Contents"]:
            s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
    repo_head_key = f"repos/l;{repo_head.repo_user_name};{repo_head.repo_name};{repo_head.last_run_at or ''};" \
                    f"{repo_head.tags_count}"
    s3_client.put_object(Body="", Bucket=bucket_name, Key=repo_head_key)


def update_repo_last_run_at(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str,
                            last_run_at: int):
    repo_head = _get_repo_head(s3_client, bucket_name, repo_user_name, repo_name) or RepoHead(
        repo_user_name, repo_name, None, tags_count=0)
    repo_head.last_run_at = last_run_at
    _create_or_update_repo_head(s3_client, bucket_name, repo_head)


def increment_repo_tags_count(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str):
    repo_head = _get_repo_head(s3_client, bucket_name, repo_user_name, repo_name) or RepoHead(
        repo_user_name, repo_name, None, tags_count=0)
    repo_head.tags_count = repo_head.tags_count + 1
    _create_or_update_repo_head(s3_client, bucket_name, repo_head)


def decrement_repo_tags_count(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str):
    repo_head = _get_repo_head(s3_client, bucket_name, repo_user_name, repo_name)
    if repo_head:
        repo_head.tags_count = repo_head.tags_count - 1
        _create_or_update_repo_head(s3_client, bucket_name, repo_head)
    else:
        raise Exception(f"No repo head is found: {repo_user_name}/{repo_name}")


def delete_repo(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str):
    repo_head_prefix = f"repos/l;{repo_user_name};{repo_name};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=repo_head_prefix)
    if "Contents" in response:
        for obj in response["Contents"]:
            s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])


def save_repo_credentials(sts_client: BaseClient, iam_client: BaseClient, secretsmanager_client: BaseClient,
                          bucket_name: str, repo_user_name: str, repo_name: str,
                          repo_credentials: RepoCredentials):
    secret_name = f"/dstack/{bucket_name}/credentials/{repo_user_name}/{repo_name}"
    credentials_data = {
        "protocol": repo_credentials.protocol.value
    }
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
            SecretId=secret_name,
            SecretString=json.dumps(credentials_data)
        )
    except Exception as e:
        if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get(
                "Code") == "ResourceNotFoundException":
            secretsmanager_client.create_secret(
                Name=secret_name,
                SecretString=json.dumps(credentials_data),
                Description="Generated by dstack",
                Tags=[
                    {
                        'Key': 'owner',
                        'Value': 'dstack'
                    },
                    {
                        'Key': 'dstack_bucket',
                        'Value': bucket_name
                    }
                ],
            )
        else:
            raise e
    role_name = runners.role_name(iam_client, bucket_name)
    account_id = sts_client.get_caller_identity()["Account"]
    secretsmanager_client.put_resource_policy(
        SecretId=secret_name,
        ResourcePolicy=json.dumps(
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
                        "Resource": "*"
                    }
                ]
            }
        )
    )
