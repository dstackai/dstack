from typing import Optional

import pytest

from dstack._internal.core.compatibility.runs import get_get_plan_excludes
from dstack._internal.server.schemas.runs import GetRunPlanRequest
from dstack._internal.server.testing.common import get_run_spec


class TestGetGetPlanExcludes:
    @pytest.mark.parametrize("reverse_offers", [None, False, True])
    def test_omits_disabled_reverse_offers(self, reverse_offers: Optional[bool]):
        kwargs = {} if reverse_offers is None else {"reverse_offers": reverse_offers}
        request = GetRunPlanRequest.model_validate(
            {"run_spec": get_run_spec(repo_id="test-repo"), **kwargs}
        )

        body = request.model_dump(exclude=get_get_plan_excludes(request))

        if reverse_offers:
            assert body["reverse_offers"] is True
        else:
            assert "reverse_offers" not in body
