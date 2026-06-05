from dstack._internal.core.compatibility.fleets import get_fleet_spec_excludes
from dstack._internal.core.compatibility.runs import get_run_spec_excludes
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.fleets import FleetConfiguration, FleetSpec
from dstack._internal.core.models.profiles import InstanceNameSelector, Profile
from dstack._internal.core.models.runs import RunSpec


class TestGetRunSpecExcludes:
    def test_excludes_unset_instances_for_old_servers(self):
        run_spec = RunSpec(
            configuration=TaskConfiguration(commands=["echo"]),
            profile=Profile(name="default"),
        )

        excludes = get_run_spec_excludes(run_spec)

        assert excludes["configuration"]["instances"] is True
        assert "instances" in excludes["profile"]

    def test_keeps_configuration_instances_when_set(self):
        run_spec = RunSpec(
            configuration=TaskConfiguration(
                commands=["echo"],
                instances=[InstanceNameSelector(name="my-fleet-0")],
            ),
            profile=Profile(name="default"),
        )

        excludes = get_run_spec_excludes(run_spec)

        assert "instances" not in excludes["configuration"]
        assert "instances" in excludes["profile"]

    def test_keeps_profile_instances_when_set(self):
        run_spec = RunSpec(
            configuration=TaskConfiguration(commands=["echo"]),
            profile=Profile(
                name="default",
                instances=[InstanceNameSelector(name="my-fleet-0")],
            ),
        )

        excludes = get_run_spec_excludes(run_spec)

        assert excludes["configuration"]["instances"] is True
        assert "instances" not in excludes["profile"]


class TestGetFleetSpecExcludes:
    def test_excludes_unset_profile_instances_for_old_servers(self):
        spec = FleetSpec(configuration=FleetConfiguration(), profile=Profile())

        excludes = get_fleet_spec_excludes(spec)

        assert excludes is not None
        assert "instances" in excludes["profile"]

    def test_keeps_profile_instances_when_set(self):
        spec = FleetSpec(configuration=FleetConfiguration(), profile=Profile())
        spec.profile.instances = [InstanceNameSelector(name="my-fleet-0")]

        excludes = get_fleet_spec_excludes(spec)

        assert excludes is not None
        assert "instances" not in excludes["profile"]
