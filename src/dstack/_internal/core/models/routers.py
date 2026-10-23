from enum import Enum
from typing import Any

from pydantic import Field, field_serializer, field_validator
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel


class RouterType(str, Enum):
    SMG = "smg"
    DYNAMO = "dynamo"


# The value `RouterType.SMG` had before the rename
_LEGACY_SMG_VALUE = "sglang"


class ReplicaGroupRouterConfig(CoreModel):
    type: Annotated[
        RouterType,
        Field(
            description=(
                "The router implementation for this replica group."
                " `smg` runs the Shepherd Model Gateway (SMG) and dstack syncs worker URLs to it."
                " `dynamo` runs the NVIDIA Dynamo frontend, which discovers workers"
                " itself via etcd"
            ),
        ),
    ] = RouterType.SMG

    @field_validator("type", mode="before")
    @classmethod
    def _accept_legacy_smg_value(cls, v: Any) -> Any:
        # Stored run specs and older clients' requests use the legacy value
        if v == _LEGACY_SMG_VALUE:
            return RouterType.SMG
        return v

    @field_serializer("type", when_used="json")
    def _serialize_type(self, v: RouterType) -> str:
        # Servers and clients < 0.22.4 reject `smg`, so keep sending and storing the legacy value
        # for one minor release. This covers client requests, server responses, and the run specs
        # stored in the DB, which older server replicas read during a rolling deployment.
        # TODO(0.23.0): Drop this serializer. When doing so, patch run specs in server responses
        # back to the legacy value for clients < 0.22.4 (see `server/compatibility/runs.py`),
        # since 0.23.* servers still support 0.22.* clients. Keep `_accept_legacy_smg_value`:
        # run specs stored with the legacy value stay in the DB.
        if v == RouterType.SMG:
            return _LEGACY_SMG_VALUE
        return v.value
