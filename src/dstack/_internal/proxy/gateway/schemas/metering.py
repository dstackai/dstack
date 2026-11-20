import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MeteringRecord(BaseModel):
    hour: datetime
    """UTC, start of the hour in which the tokens were counted."""
    project_id: uuid.UUID
    user_id: uuid.UUID
    run_id: uuid.UUID
    export_id: Optional[uuid.UUID] = None
    """The export that the requests came through. `None` for a project's own models."""
    input_tokens: int
    """Includes `cached_input_tokens`."""
    cached_input_tokens: int
    output_tokens: int


class MeteringBatch(BaseModel):
    batch_no: int
    created_at: datetime
    records: list[MeteringRecord]


class CollectMeteringRequest(BaseModel):
    after: int
    """The number of the last batch that the server has saved."""
    limit: int


class CollectMeteringResponse(BaseModel):
    batches: list[MeteringBatch]
