import pytest

from dstack._internal.core.compatibility.gpus import get_list_gpus_excludes
from dstack._internal.core.compatibility.runs import get_get_plan_excludes
from dstack._internal.server.schemas.gpus import ListGpusRequest
from dstack._internal.server.schemas.runs import GetRunPlanRequest
from dstack._internal.server.testing.common import get_run_spec


class TestOfferRequestCompatibility:
    @pytest.mark.parametrize(
        ("request_type", "get_excludes", "field"),
        [
            (GetRunPlanRequest, get_get_plan_excludes, "reverse_offers"),
            (ListGpusRequest, get_list_gpus_excludes, "reverse"),
        ],
    )
    @pytest.mark.parametrize("reverse", [None, False, True])
    def test_omits_disabled_sort_flag(self, request_type, get_excludes, field, reverse):
        kwargs = {} if reverse is None else {field: reverse}
        request = request_type(run_spec=get_run_spec(repo_id="test-repo"), **kwargs)
        body = request.model_dump(exclude=get_excludes(request))

        if reverse:
            assert body[field] is True
        else:
            assert field not in body
