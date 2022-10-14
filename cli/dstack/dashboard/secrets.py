from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from dstack.backend import load_backend, Secret

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


class SecretItem(BaseModel):
    secret_name: str
    secret_value: str


class QuerySecretsResponse(BaseModel):
    secrets: List[SecretItem]


class AddOrUpdateSecretRequest(BaseModel):
    secret_name: str
    secret_value: str


class DeleteSecretRequest(BaseModel):
    secret_name: str


@router.get("/query", response_model=QuerySecretsResponse)
async def query() -> QuerySecretsResponse:
    backend = load_backend()
    secret_names = backend.list_secret_names()
    return QuerySecretsResponse(
        secrets=[SecretItem(secret_name=secret_name,
                            secret_value=backend.get_secret(secret_name).secret_value) for secret_name in secret_names])


@router.post("/add")
async def delete(request: AddOrUpdateSecretRequest):
    backend = load_backend()
    backend.add_secret(Secret(request.secret_name, request.secret_value))


@router.post("/update")
async def delete(request: AddOrUpdateSecretRequest):
    backend = load_backend()
    backend.update_secret(Secret(request.secret_name, request.secret_value))


@router.post("/delete")
async def delete(request: DeleteSecretRequest):
    backend = load_backend()
    backend.delete_secret(request.secret_name)
