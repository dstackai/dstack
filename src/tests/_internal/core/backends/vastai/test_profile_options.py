import pytest

from dstack._internal.core.backends.vastai.profile_options import (
    VastAIOfferOrder,
    VastAIProfileOptions,
)
from dstack._internal.utils.combine import CombineError


class TestVastAIProfileOptionsCombine:
    def test_combine_empty_options(self):
        a = VastAIProfileOptions()
        b = VastAIProfileOptions()
        result = a.combine(b)
        assert result == VastAIProfileOptions()

    def test_combine_all_fields_set(self):
        a = VastAIProfileOptions(
            offer_order=VastAIOfferOrder.PRICE,
            min_reliability=0.7,
            min_score=100,
        )
        b = VastAIProfileOptions(
            offer_order=VastAIOfferOrder.PRICE,
            min_reliability=0.95,
            min_score=300,
        )
        a_combine_b = a.combine(b)
        assert a_combine_b.offer_order == VastAIOfferOrder.PRICE
        assert a_combine_b.min_reliability == 0.95
        assert a_combine_b.min_score == 300
        b_combine_a = b.combine(a)
        assert b_combine_a.offer_order == VastAIOfferOrder.PRICE
        assert b_combine_a.min_reliability == 0.95
        assert b_combine_a.min_score == 300

    def test_combine_one_has_all_fields_set(self):
        a = VastAIProfileOptions(
            offer_order=VastAIOfferOrder.PRICE,
            min_reliability=0.7,
            min_score=100,
        )
        b = VastAIProfileOptions()
        assert a.combine(b) == a
        assert b.combine(a) == a

    def test_combine_conflicting_offer_order_raises(self):
        a = VastAIProfileOptions(offer_order=VastAIOfferOrder.PRICE)
        b = VastAIProfileOptions(offer_order=VastAIOfferOrder.SCORE)
        with pytest.raises(CombineError):
            a.combine(b)
