from typing import Optional

import pytest

from dstack._internal.core.backends.vastai.profile_options import VastAIProfileOptions
from dstack._internal.core.compatibility.runs import (
    get_get_plan_excludes,
    get_job_spec_excludes,
    get_run_spec_excludes,
)
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobSpec, Requirements
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


class TestGetRunSpecExcludes:
    @pytest.mark.parametrize("min_inet_down", [None, 8000])
    def test_omits_unset_vastai_min_inet_down(self, min_inet_down: Optional[int]):
        backend_options = [VastAIProfileOptions(min_score=100, min_inet_down=min_inet_down)]
        run_spec = get_run_spec(
            repo_id="test-repo",
            profile=Profile(name="default", backend_options=backend_options),
            configuration=TaskConfiguration(commands=["echo"], backend_options=backend_options),
        )

        body = run_spec.model_dump(exclude=get_run_spec_excludes(run_spec))

        for options in [
            body["profile"]["backend_options"][0],
            body["configuration"]["backend_options"][0],
        ]:
            assert options["min_score"] == 100
            if min_inet_down is None:
                assert "min_inet_down" not in options
            else:
                assert options["min_inet_down"] == min_inet_down


class TestGetJobSpecExcludes:
    @pytest.mark.parametrize("min_inet_down", [None, 8000])
    def test_omits_unset_vastai_min_inet_down(self, min_inet_down: Optional[int]):
        job_spec = JobSpec(
            job_num=0,
            job_name="test-run-0-0",
            commands=["echo"],
            env={},
            image_name="dstackai/base",
            requirements=Requirements(
                resources=ResourcesSpec(),
                backend_options=[VastAIProfileOptions(min_inet_down=min_inet_down)],
            ),
        )

        body = job_spec.model_dump(exclude=get_job_spec_excludes([job_spec]))

        options = body["requirements"]["backend_options"][0]
        if min_inet_down is None:
            assert "min_inet_down" not in options
        else:
            assert options["min_inet_down"] == min_inet_down
