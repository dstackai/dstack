import pytest
from pydantic import ValidationError

from dstack._internal.core.backends.vastai.profile_options import VastAIProfileOptions
from dstack._internal.core.compatibility.common import get_profile_excludes
from dstack._internal.core.models.common import EntityReference
from dstack._internal.core.models.profiles import (
    FleetInstanceSelector,
    InstanceHostnameSelector,
    InstanceNameSelector,
    Profile,
)


class TestValidateProfileBackendOptions:
    def test_duplicate_backend_type_raises_validation_error(self):
        with pytest.raises(ValidationError, match="duplicate entry for backend 'vastai'"):
            Profile(
                backend_options=[
                    VastAIProfileOptions(min_score=100),
                    VastAIProfileOptions(min_score=200),
                ]
            )

    def test_single_entry_per_backend_is_valid(self):
        profile = Profile(backend_options=[VastAIProfileOptions(min_score=100)])
        assert profile.backend_options is not None
        assert len(profile.backend_options) == 1

    def test_none_backend_options_is_valid(self):
        profile = Profile(backend_options=None)
        assert profile.backend_options is None

    def test_empty_list_backend_options_is_valid(self):
        profile = Profile(backend_options=[])
        assert profile.backend_options == []


class TestProfileInstances:
    def test_string_is_parsed_as_instance_name_selector(self):
        profile = Profile.parse_obj({"instances": ["my-fleet-1"]})

        assert profile.instances == [InstanceNameSelector(name="my-fleet-1")]

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ({"name": "my-fleet-1"}, InstanceNameSelector(name="my-fleet-1")),
            ({"hostname": "worker-1"}, InstanceHostnameSelector(hostname="worker-1")),
            (
                {"fleet": "my-fleet", "instance": 3},
                FleetInstanceSelector(fleet="my-fleet", instance=3),
            ),
            (
                {"fleet": "other-project/my-fleet", "instance": 3},
                FleetInstanceSelector(fleet="other-project/my-fleet", instance=3),
            ),
        ],
    )
    def test_object_selectors_are_parsed(self, value, expected):
        profile = Profile.parse_obj({"instances": [value]})

        assert profile.instances == [expected]

    def test_parses_fleet_selector_object_notation(self):
        profile = Profile.parse_obj(
            {"instances": [{"fleet": {"project": "main", "name": "my-fleet"}, "instance": 0}]}
        )

        assert profile.instances == [
            FleetInstanceSelector(
                fleet=EntityReference(project="main", name="my-fleet"), instance=0
            )
        ]

    @pytest.mark.parametrize(
        "value",
        [
            "",
            {"name": "my-fleet-1", "hostname": "worker-1"},
            {"name": ""},
            {"hostname": ""},
            {"fleet": "", "instance": 0},
            {"fleet": "project/name/extra", "instance": 0},
            {"fleet": "my-fleet"},
            {"fleet": "my-fleet", "instance": -1},
            {"hostname": "worker-1", "extra": "value"},
        ],
    )
    def test_invalid_selector_is_rejected(self, value):
        with pytest.raises(ValidationError):
            Profile.parse_obj({"instances": [value]})

    def test_empty_instances_list_is_rejected(self):
        with pytest.raises(ValidationError):
            Profile.parse_obj({"instances": []})


class TestProfileInstancesCompatibilityExcludes:
    def test_excludes_unset_instances(self):
        profile = Profile()

        assert "instances" not in profile.dict(exclude=get_profile_excludes(profile))

    def test_preserves_configured_instances(self):
        profile = Profile(instances=[InstanceNameSelector(name="my-fleet-1")])

        assert profile.dict(exclude=get_profile_excludes(profile))["instances"] == [
            {"name": "my-fleet-1"}
        ]
