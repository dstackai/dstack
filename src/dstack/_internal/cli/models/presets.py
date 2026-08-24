from datetime import datetime
from typing import List, Literal, Optional, Union

from pydantic import Field, PositiveInt
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import PresetConfiguration
from dstack._internal.core.models.presets import PortablePreset


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
