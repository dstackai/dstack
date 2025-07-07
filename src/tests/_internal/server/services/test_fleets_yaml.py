from dstack._internal.core.models.fleets import FleetConfiguration, FleetSpec
from dstack._internal.core.models.profiles import Profile
from dstack._internal.server.services.fleets import fleet_configuration_to_yaml


def test_fleet_configuration_to_yaml():
    """Test that fleet configuration is correctly converted to YAML."""
    # Create a simple fleet configuration
    config = FleetConfiguration(
        name="test-fleet",
        nodes=2,
        resources={"gpu": "24GB"},
    )

    spec = FleetSpec(
        configuration=config,
        profile=Profile(name="test-profile"),
    )

    # Convert to YAML
    yaml_content = fleet_configuration_to_yaml(spec)

    # Verify the YAML contains expected content
    assert "name: test-fleet" in yaml_content
    assert "min: 2" in yaml_content  # nodes.min
    assert "max: 2" in yaml_content  # nodes.max
    assert "gpu:" in yaml_content
    assert "type: fleet" in yaml_content


def test_fleet_configuration_to_yaml_with_ssh():
    """Test that SSH fleet configuration is correctly converted to YAML."""
    # Create an SSH fleet configuration
    config = FleetConfiguration(
        name="ssh-fleet",
        ssh_config={
            "user": "ubuntu",
            "hosts": ["192.168.1.100", "192.168.1.101"],
        },
    )

    spec = FleetSpec(
        configuration=config,
        profile=Profile(name="test-profile"),
    )

    # Convert to YAML
    yaml_content = fleet_configuration_to_yaml(spec)

    # Verify the YAML contains expected content
    assert "name: ssh-fleet" in yaml_content
    assert "user: ubuntu" in yaml_content
    assert "192.168.1.100" in yaml_content
    assert "192.168.1.101" in yaml_content
    assert "type: fleet" in yaml_content
