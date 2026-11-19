"""Versioned minute aggregates shared by Gateway and its receivers."""

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Counter = Annotated[int, Field(strict=True, ge=0)]
Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=128)]


class UsageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AuthorizedSubject(UsageModel):
    consumer_subject_id: Identifier


class UsageKey(AuthorizedSubject):
    service_id: Identifier

    def __hash__(self) -> int:
        return hash((self.consumer_subject_id, self.service_id))


class TokenUsage(UsageModel):
    prompt_tokens: Counter = 0
    cached_prompt_tokens: Counter = 0
    completion_tokens: Counter = 0
    total_tokens: Counter = 0

    @model_validator(mode="after")
    def check_totals(self) -> Self:
        if self.cached_prompt_tokens > self.prompt_tokens:
            raise ValueError("Cached tokens exceed prompt tokens")
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("Total tokens must equal prompt plus completion")
        return self


class UsageEntry(TokenUsage, UsageKey):
    unknown_usage_attempts: Counter = 0

    @property
    def key(self) -> UsageKey:
        return UsageKey(consumer_subject_id=self.consumer_subject_id, service_id=self.service_id)


class UsageBatch(UsageModel):
    batch_id: Identifier
    interval_start: datetime
    interval_end: datetime
    entries: list[UsageEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_interval_and_keys(self) -> Self:
        for value in (self.interval_start, self.interval_end):
            if value.utcoffset() != timedelta(0) or value.second or value.microsecond:
                raise ValueError("Intervals must use UTC minute boundaries")
        if self.interval_end - self.interval_start != timedelta(seconds=60):
            raise ValueError("Interval must be exactly sixty seconds")
        keys = [entry.key for entry in self.entries]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate usage key")
        return self


class _UsageCheckpoint(UsageModel):
    active_batch: UsageBatch
    pending_batches: list[UsageBatch] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_batch_ids(self) -> Self:
        batches = [*self.pending_batches, self.active_batch]
        if len({batch.batch_id for batch in batches}) != len(batches):
            raise ValueError("Duplicate batch ID")
        previous_end = None
        for batch in batches:
            if previous_end is not None and batch.interval_start < previous_end:
                raise ValueError("Overlapping or unordered batch intervals")
            previous_end = batch.interval_end
        return self


class UsageCheckpoint(_UsageCheckpoint):
    schema_version: Literal[2] = 2
    drain_state: Literal["ingress", "ingress_stopped", "waiting", "sealed"] | None = Field(
        default=None, exclude_if=lambda state: state is None
    )
    """ingress_stopped records a clean collector stop while old Nginx workers can still deliver."""

    @model_validator(mode="after")
    def check_sealed(self) -> Self:
        if self.drain_state == "sealed" and self.active_batch.entries:
            raise ValueError("A sealed checkpoint cannot have unclosed entries")
        return self


class LegacyUsageCheckpoint(_UsageCheckpoint):
    """Read-only local format used before source identity moved to server."""

    schema_version: Literal[1] = 1
    collector_id: Identifier


class _UsageBatchPage(UsageModel):
    batches: list[UsageBatch] = Field(default_factory=list, max_length=100)
    has_more: bool = False

    @model_validator(mode="after")
    def check_ids(self) -> Self:
        if len({batch.batch_id for batch in self.batches}) != len(self.batches):
            raise ValueError("Duplicate batch ID")
        return self


class UsageBatchPage(_UsageBatchPage):
    schema_version: Literal[2] = 2


class LegacyUsageBatchPage(_UsageBatchPage):
    """Read-only compatibility for Gateways upgraded after the server."""

    schema_version: Literal[1] = 1
    collector_id: Identifier


class UsageAckRequest(UsageModel):
    batch_ids: list[Identifier] = Field(min_length=1, max_length=100)


class UsageAckResponse(UsageModel):
    acknowledged_batch_ids: list[Identifier]


class UsageDrainResponse(UsageModel):
    sealed: Annotated[bool, Field(strict=True)]
    empty: Annotated[bool, Field(strict=True)]

    @model_validator(mode="after")
    def check_empty(self) -> Self:
        if self.empty and not self.sealed:
            raise ValueError("An unsealed source cannot certify an empty drain")
        return self
