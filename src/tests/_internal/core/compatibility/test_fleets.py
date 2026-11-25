from dstack._internal.core.backends.vastai.profile_options import VastAIProfileOptions
from dstack._internal.core.compatibility.fleets import get_fleet_spec_excludes
from dstack._internal.core.models.fleets import FleetSpec
from dstack._internal.core.models.profiles import Profile
from dstack._internal.server.testing.common import get_fleet_configuration, get_fleet_spec


def _fleet_spec(min_inet_down=None) -> FleetSpec:
    conf = get_fleet_configuration()
    conf.backend_options = [VastAIProfileOptions(min_score=100, min_inet_down=min_inet_down)]
    profile = Profile(backend_options=[VastAIProfileOptions(min_inet_down=min_inet_down)])
    return get_fleet_spec(conf=conf, profile=profile)


class TestGetFleetSpecExcludes:
    def test_omits_unset_vastai_min_inet_down(self):
        spec = _fleet_spec()

        body = spec.model_dump(exclude=get_fleet_spec_excludes(spec))

        assert body["configuration"]["backend_options"] == [
            {"type": "vastai", "offer_order": None, "min_reliability": None, "min_score": 100}
        ]
        assert "min_inet_down" not in body["profile"]["backend_options"][0]

    def test_keeps_set_vastai_min_inet_down(self):
        spec = _fleet_spec(min_inet_down=8000)

        body = spec.model_dump(exclude=get_fleet_spec_excludes(spec))

        assert body["configuration"]["backend_options"][0]["min_inet_down"] == 8000
        assert body["profile"]["backend_options"][0]["min_inet_down"] == 8000
