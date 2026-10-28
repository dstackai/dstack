from typing import Optional

import pytest

from dstack._internal.core.compatibility.gpus import get_list_gpus_excludes
from dstack._internal.server.schemas.gpus import ListGpusRequest
from dstack._internal.server.testing.common import get_run_spec


class TestGetListGpusExcludes:
    @pytest.mark.parametrize("reverse", [None, False, True])
    def test_omits_disabled_reverse(self, reverse: Optional[bool]):
        kwargs = {} if reverse is None else {"reverse": reverse}
        request = ListGpusRequest.model_validate(
            {"run_spec": get_run_spec(repo_id="test-repo"), **kwargs}
        )

        body = request.model_dump(exclude=get_list_gpus_excludes(request))

        if reverse:
            assert body["reverse"] is True
        else:
            assert "reverse" not in body
