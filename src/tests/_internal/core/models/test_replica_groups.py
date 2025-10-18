"""Tests for Named Replica Groups functionality"""
import pytest

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import (
    ServiceConfiguration,
    parse_run_configuration,
)
from dstack._internal.core.models.resources import CPUSpec, GPUSpec, Range, ResourcesSpec
from dstack._internal.core.models.runs import get_normalized_replica_groups


class TestReplicaGroupConfiguration:
    """Test replica group configuration parsing and validation"""

    def test_basic_replica_groups(self):
        """Test basic replica groups configuration"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replica_groups": [
                {
                    "name": "h100-group",
                    "replicas": 1,
                    "resources": {"gpu": "H100:1"},
                },
                {
                    "name": "rtx5090-group",
                    "replicas": 2,
                    "resources": {"gpu": "RTX5090:1"},
                },
            ],
        }
        
        parsed = parse_run_configuration(conf)
        assert isinstance(parsed, ServiceConfiguration)
        assert parsed.replica_groups is not None
        assert len(parsed.replica_groups) == 2
        
        # Check first group
        assert parsed.replica_groups[0].name == "h100-group"
        assert parsed.replica_groups[0].replicas == Range(min=1, max=1)
        assert parsed.replica_groups[0].resources.gpu.name == ["H100"]
        
        # Check second group
        assert parsed.replica_groups[1].name == "rtx5090-group"
        assert parsed.replica_groups[1].replicas == Range(min=2, max=2)
        assert parsed.replica_groups[1].resources.gpu.name == ["RTX5090"]

    def test_replica_groups_with_ranges(self):
        """Test replica groups with autoscaling ranges"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replica_groups": [
                {
                    "name": "fixed-group",
                    "replicas": 1,
                    "resources": {"gpu": "H100:1"},
                },
                {
                    "name": "scalable-group",
                    "replicas": "1..3",  # Range
                    "resources": {"gpu": "RTX5090:1"},
                },
            ],
            "scaling": {
                "metric": "rps",
                "target": 10,
            },
        }
        
        parsed = parse_run_configuration(conf)
        assert parsed.replica_groups is not None
        assert len(parsed.replica_groups) == 2
        
        # Fixed group
        assert parsed.replica_groups[0].replicas == Range(min=1, max=1)
        
        # Scalable group
        assert parsed.replica_groups[1].replicas == Range(min=1, max=3)

    def test_replica_groups_with_profile_params(self):
        """Test replica groups can override profile parameters"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            # Service-level settings
            "backends": ["aws"],
            "regions": ["us-west-2"],
            "replica_groups": [
                {
                    "name": "aws-group",
                    "replicas": 1,
                    "resources": {"gpu": "H100:1"},
                    # Inherits backends/regions from service
                },
                {
                    "name": "runpod-group",
                    "replicas": 1,
                    "resources": {"gpu": "RTX5090:1"},
                    # Override backends
                    "backends": ["runpod"],
                    "regions": ["eu-west-1"],
                },
            ],
        }
        
        parsed = parse_run_configuration(conf)
        
        # First group inherits from service (doesn't specify backends/regions)
        assert parsed.replica_groups[0].backends is None
        assert parsed.replica_groups[0].regions is None
        
        # Second group overrides
        assert parsed.replica_groups[1].backends == ["runpod"]
        assert parsed.replica_groups[1].regions == ["eu-west-1"]

    def test_replica_groups_xor_replicas(self):
        """Test that replica_groups and replicas are mutually exclusive"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replicas": 2,  # Old format
            "replica_groups": [  # New format
                {
                    "name": "group1",
                    "replicas": 1,
                    "resources": {"gpu": "H100:1"},
                }
            ],
        }
        
        with pytest.raises(
            ConfigurationError,
            match="Cannot specify both 'replicas' and 'replica_groups'",
        ):
            parse_run_configuration(conf)

    def test_replica_groups_unique_names(self):
        """Test that replica group names must be unique"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replica_groups": [
                {
                    "name": "group1",
                    "replicas": 1,
                    "resources": {"gpu": "H100:1"},
                },
                {
                    "name": "group1",  # Duplicate!
                    "replicas": 1,
                    "resources": {"gpu": "RTX5090:1"},
                },
            ],
        }
        
        with pytest.raises(
            ConfigurationError,
            match="Replica group names must be unique",
        ):
            parse_run_configuration(conf)

    def test_replica_groups_empty_name(self):
        """Test that replica group names cannot be empty"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replica_groups": [
                {
                    "name": "",  # Empty name
                    "replicas": 1,
                    "resources": {"gpu": "H100:1"},
                }
            ],
        }
        
        with pytest.raises(
            ConfigurationError,
            match="Group name cannot be empty",
        ):
            parse_run_configuration(conf)

    def test_replica_groups_range_requires_scaling(self):
        """Test that replica ranges require scaling configuration"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replica_groups": [
                {
                    "name": "scalable-group",
                    "replicas": "1..3",
                    "resources": {"gpu": "RTX5090:1"},
                }
            ],
            # Missing scaling!
        }
        
        with pytest.raises(
            ConfigurationError,
            match="When any replica group has a range, 'scaling' must be specified",
        ):
            parse_run_configuration(conf)

    def test_replica_groups_cannot_be_empty(self):
        """Test that replica_groups list cannot be empty"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replica_groups": [],  # Empty list
        }
        
        with pytest.raises(
            ConfigurationError,
            match="replica_groups cannot be empty",
        ):
            parse_run_configuration(conf)


class TestReplicaGroupNormalization:
    """Test get_normalized_replica_groups helper"""

    def test_normalize_new_format(self):
        """Test normalization with replica_groups format"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replica_groups": [
                {
                    "name": "group1",
                    "replicas": 1,
                    "resources": {"gpu": "H100:1"},
                },
                {
                    "name": "group2",
                    "replicas": 2,
                    "resources": {"gpu": "RTX5090:1"},
                },
            ],
        }
        
        parsed = parse_run_configuration(conf)
        normalized = get_normalized_replica_groups(parsed)
        
        assert len(normalized) == 2
        assert normalized[0].name == "group1"
        assert normalized[1].name == "group2"

    def test_normalize_legacy_format(self):
        """Test normalization converts legacy replicas to default group"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replicas": 3,
            "resources": {"gpu": "H100:1"},
            "backends": ["aws"],
            "regions": ["us-west-2"],
        }
        
        parsed = parse_run_configuration(conf)
        normalized = get_normalized_replica_groups(parsed)
        
        # Should create single "default" group
        assert len(normalized) == 1
        assert normalized[0].name == "default"
        assert normalized[0].replicas == Range(min=3, max=3)
        assert normalized[0].resources.gpu.name == ["H100"]
        
        # Should inherit profile params
        assert normalized[0].backends == ["aws"]
        assert normalized[0].regions == ["us-west-2"]

    def test_normalize_legacy_with_range(self):
        """Test normalization with legacy autoscaling"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replicas": "1..5",
            "resources": {"gpu": "RTX5090:1"},
            "scaling": {
                "metric": "rps",
                "target": 10,
            },
        }
        
        parsed = parse_run_configuration(conf)
        normalized = get_normalized_replica_groups(parsed)
        
        assert len(normalized) == 1
        assert normalized[0].name == "default"
        assert normalized[0].replicas == Range(min=1, max=5)


class TestReplicaGroupAutoscaling:
    """Test autoscaling behavior with replica groups"""

    def test_autoscalable_group_detection(self):
        """Test identifying which groups are autoscalable"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replica_groups": [
                {
                    "name": "fixed",
                    "replicas": 1,
                    "resources": {"gpu": "H100:1"},
                },
                {
                    "name": "scalable",
                    "replicas": "1..3",
                    "resources": {"gpu": "RTX5090:1"},
                },
            ],
            "scaling": {
                "metric": "rps",
                "target": 10,
            },
        }
        
        parsed = parse_run_configuration(conf)
        
        # Fixed group: min == max
        assert parsed.replica_groups[0].replicas.min == parsed.replica_groups[0].replicas.max
        
        # Scalable group: min != max
        assert parsed.replica_groups[1].replicas.min != parsed.replica_groups[1].replicas.max

    def test_multiple_autoscalable_groups(self):
        """Test multiple groups can be autoscalable"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replica_groups": [
                {
                    "name": "scalable-1",
                    "replicas": "1..3",
                    "resources": {"gpu": "H100:1"},
                },
                {
                    "name": "scalable-2",
                    "replicas": "2..5",
                    "resources": {"gpu": "RTX5090:1"},
                },
            ],
            "scaling": {
                "metric": "rps",
                "target": 10,
            },
        }
        
        parsed = parse_run_configuration(conf)
        
        # Both are autoscalable
        assert parsed.replica_groups[0].replicas.min != parsed.replica_groups[0].replicas.max
        assert parsed.replica_groups[1].replicas.min != parsed.replica_groups[1].replicas.max


class TestBackwardCompatibility:
    """Test backward compatibility with existing configurations"""

    def test_legacy_service_config(self):
        """Test that legacy service configs still work"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replicas": 2,
            "resources": {"gpu": "A100:1"},
        }
        
        parsed = parse_run_configuration(conf)
        
        # Should parse successfully
        assert isinstance(parsed, ServiceConfiguration)
        assert parsed.replicas == Range(min=2, max=2)
        assert parsed.replica_groups is None  # Not using new format

    def test_legacy_autoscaling_config(self):
        """Test legacy autoscaling configurations"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replicas": "0..5",
            "resources": {"gpu": "A100:1"},
            "scaling": {
                "metric": "rps",
                "target": 10,
            },
        }
        
        parsed = parse_run_configuration(conf)
        
        # Should parse successfully
        assert parsed.replicas == Range(min=0, max=5)
        assert parsed.scaling is not None

    def test_normalization_preserves_all_profile_params(self):
        """Test that normalization copies all ProfileParams fields"""
        conf = {
            "type": "service",
            "commands": ["python3 app.py"],
            "port": 8000,
            "replicas": 1,
            "resources": {"gpu": "H100:1"},
            "backends": ["aws"],
            "regions": ["us-east-1"],
            "instance_types": ["p4d.24xlarge"],
            "spot_policy": "spot",
            "max_price": 10.0,
        }
        
        parsed = parse_run_configuration(conf)
        normalized = get_normalized_replica_groups(parsed)
        
        # Check all fields are copied
        group = normalized[0]
        assert group.backends == ["aws"]
        assert group.regions == ["us-east-1"]
        assert group.instance_types == ["p4d.24xlarge"]
        assert group.spot_policy == "spot"
        assert group.max_price == 10.0

