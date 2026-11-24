from datetime import datetime
from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field, PositiveInt

from dstack._internal.cli.models.preset_agent import (
    PresetSessionState,
    PresetSessionStatus,
    PresetTrial,
)
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import PresetConfiguration
from dstack._internal.core.models.presets import AnyPresetConstraints, PortablePreset


class BasePreset(CoreModel):
    id: str
    name: Optional[str] = None
    # When the preset was created where it came from: the creation session
    # locally, the registry for a pulled one.
    created_at: datetime


class UnverifiedPreset(BasePreset):
    """A preset whose creation has not passed verification: running,
    interrupted, or failed."""

    status: Literal["running", "interrupted", "failed"]
    configuration: PresetConfiguration


class VerifiedPreset(BasePreset, PortablePreset):
    """A preset whose creation passed verification, with that session attached."""

    status: Literal["verified"] = "verified"
    configuration: PresetConfiguration
    # The session's `trials/<n>` that won verification and became this preset.
    best_trial: PositiveInt


class PulledPreset(BasePreset, PortablePreset):
    """A portable preset pulled from the registry."""

    status: Literal["pulled"] = "pulled"


AnyStoredPreset = Annotated[Union[VerifiedPreset, PulledPreset], Field(discriminator="status")]


class PresetListOutput(CoreModel):
    presets: List[AnyStoredPreset]


class PresetTrialsSummary(CoreModel):
    """Built by the CLI for `dstack preset list`."""

    count: int
    # The trial with the highest tok/s that met the constraints.
    best: Optional[PresetTrial] = None
    # The trial with the highest tok/s but broke the constraints.
    best_failed: Optional[PresetTrial] = None
    # One value per trial in order, for the sparkline; None for a trial that
    # produced no benchmark.
    series: list[Optional[float]]
    # Parallel to `series`: True where the trial broke the constraints.
    failed: list[bool]
    # The hardware of the shown trial, `best` or else `best_failed`; when neither
    # exists, of the last trial that recorded it, so the session still shows what
    # it ran on.
    gpu: Optional[str] = None


class PresetSessionEntry(CoreModel):
    """Built by the CLI for `dstack preset list`."""

    id: str
    state: PresetSessionState
    name: Optional[str]
    status: PresetSessionStatus
    trials: PresetTrialsSummary
    verification: Optional[str]
    constraints: Optional[AnyPresetConstraints]
