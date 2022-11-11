from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from dstack.backend import load_backend, Secret
from dstack.repo import RepoAddress

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


class SecretItem(BaseModel):
    secret_name: str
    secret_value: str


class QuerySecretsResponse(BaseModel):
    secrets: List[SecretItem]


class AddOrUpdateSecretRequest(BaseModel):
    repo_host_name: str
    repo_port: Optional[int]
    repo_user_name: str
    repo_name: str
    secret_name: str
    secret_value: str


class DeleteSecretRequest(BaseModel):
    repo_host_name: str
    repo_port: Optional[int]
    repo_user_name: str
    repo_name: str
    secret_name: str


@router.get("/query", response_model=QuerySecretsResponse)
async def query(repo_host_name: str, repo_port: Optional[int], repo_user_name: str, repo_name: str) -> QuerySecretsResponse:
    backend = load_backend()
    repo_address = RepoAddress(repo_host_name, repo_port, repo_user_name, repo_name)
    secret_names = backend.list_secret_names(repo_address)
    return QuerySecretsResponse(secrets=[
        SecretItem(secret_name=secret_name, secret_value=backend.get_secret(repo_address, secret_name).secret_value)
        for secret_name in secret_names])


@router.post("/add")
async def delete(request: AddOrUpdateSecretRequest):
    backend = load_backend()
    backend.add_secret(
        RepoAddress(request.repo_host_name, request.repo_port, request.repo_user_name, request.repo_name),
        Secret(request.secret_name, request.secret_value))


@router.post("/update")
async def delete(request: AddOrUpdateSecretRequest):
    backend = load_backend()
    backend.update_secret(
        RepoAddress(request.repo_host_name, request.repo_port, request.repo_user_name, request.repo_name),
        Secret(request.secret_name, request.secret_value))


@router.post("/delete")
async def delete(request: DeleteSecretRequest):
    backend = load_backend()
    backend.delete_secret(
        RepoAddress(request.repo_host_name, request.repo_port, request.repo_user_name, request.repo_name),
        request.secret_name)
