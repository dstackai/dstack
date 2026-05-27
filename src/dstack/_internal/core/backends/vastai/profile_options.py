from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import Field

from dstack._internal.core.backends.base.profile_options import BackendProfileOptions
from dstack._internal.utils.combine import get_max_optional, get_single_value_optional


class VastAIOfferOrder(str, Enum):
    SCORE = "score"
    PRICE = "price"


VASTAI_DEFAULT_OFFER_ORDER = VastAIOfferOrder.SCORE
VASTAI_DEFAULT_MIN_RELIABILITY = 0.9


class VastAIProfileOptions(BackendProfileOptions["VastAIProfileOptions"]):
    type: Literal["vastai"] = "vastai"
    offer_order: Annotated[
        Optional[VastAIOfferOrder],
        Field(
            description=(
                "Controls the order in which offers are considered for provisioning."
                " Use `score` to prioritize the highest overall score first"
                " (the default order in the Vast.ai console),"
                " or `price` to prioritize the lowest-cost offers first."
                " Lower-cost offers are often less reliable,"
                " so consider applying stricter filters when using `price`."
                f" Defaults to `{VASTAI_DEFAULT_OFFER_ORDER.value}`"
            )
        ),
    ] = None
    min_reliability: Annotated[
        Optional[float],
        Field(
            description=(
                "The minimum reliability threshold for offers, on a scale from `0` to `1`."
                f" Defaults to `{VASTAI_DEFAULT_MIN_RELIABILITY}`"
            ),
            ge=0,
            le=1,
        ),
    ] = None
    min_score: Annotated[
        Optional[int],
        Field(
            description=(
                "The minimum overall score required for offers to be considered."
                " The scoring scale varies and may require experimentation."
                " Starting with a value in the low hundreds is generally recommended"
            ),
            ge=0,
        ),
    ] = None

    def combine(self, other: "VastAIProfileOptions") -> "VastAIProfileOptions":
        return VastAIProfileOptions(
            offer_order=get_single_value_optional(self.offer_order, other.offer_order),
            min_reliability=get_max_optional(self.min_reliability, other.min_reliability),
            min_score=get_max_optional(self.min_score, other.min_score),
        )
