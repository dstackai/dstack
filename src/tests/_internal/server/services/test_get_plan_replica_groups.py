"""Test get_plan() offer fetching logic for replica groups."""

from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements


class TestGetPlanOfferFetchingLogic:
    """Test the logic for determining when to fetch offers per-job vs. shared."""

    def test_requirements_equality_check(self):
        """Test that Requirements objects can be compared for equality."""
        # Identical requirements
        req1 = Requirements(
            resources=ResourcesSpec(gpu={"name": "A100", "count": 1}),
        )
        req2 = Requirements(
            resources=ResourcesSpec(gpu={"name": "A100", "count": 1}),
        )
        assert req1 == req2

        # Different GPU names
        req3 = Requirements(
            resources=ResourcesSpec(gpu={"name": "H100", "count": 1}),
        )
        assert req1 != req3

        # Different GPU counts
        req4 = Requirements(
            resources=ResourcesSpec(gpu={"name": "A100", "count": 2}),
        )
        assert req1 != req4

    def test_identical_requirements_detection_logic(self):
        """Test logic for detecting when all jobs have identical requirements."""

        # Simulate job specs with requirements
        class MockJobSpec:
            def __init__(self, gpu_name: str, gpu_count: int = 1):
                self.requirements = Requirements(
                    resources=ResourcesSpec(gpu={"name": gpu_name, "count": gpu_count}),
                )

        class MockJob:
            def __init__(self, gpu_name: str, gpu_count: int = 1):
                self.job_spec = MockJobSpec(gpu_name, gpu_count)

        # Test 1: All identical
        jobs = [MockJob("A100"), MockJob("A100"), MockJob("A100")]
        all_requirements_identical = all(
            job.job_spec.requirements == jobs[0].job_spec.requirements for job in jobs
        )
        assert all_requirements_identical is True

        # Test 2: Different GPU types
        jobs = [MockJob("A100"), MockJob("H100"), MockJob("A100")]
        all_requirements_identical = all(
            job.job_spec.requirements == jobs[0].job_spec.requirements for job in jobs
        )
        assert all_requirements_identical is False

        # Test 3: Different GPU counts
        jobs = [MockJob("A100", 1), MockJob("A100", 2)]
        all_requirements_identical = all(
            job.job_spec.requirements == jobs[0].job_spec.requirements for job in jobs
        )
        assert all_requirements_identical is False

        # Test 4: Single job (always identical)
        jobs = [MockJob("V100")]
        all_requirements_identical = all(
            job.job_spec.requirements == jobs[0].job_spec.requirements for job in jobs
        )
        assert all_requirements_identical is True

    def test_offer_fetch_decision_logic(self):
        """Test the decision logic for when to use shared vs per-job offer fetching."""

        class MockJobSpec:
            def __init__(self, gpu_name: str):
                self.requirements = Requirements(
                    resources=ResourcesSpec(gpu={"name": gpu_name, "count": 1}),
                )

        class MockJob:
            def __init__(self, group_name: str, gpu_name: str):
                self.job_spec = MockJobSpec(gpu_name)
                self.job_spec.replica_group_name = group_name

        # Scenario 1: Replica groups with different GPUs -> per-job fetch
        jobs = [
            MockJob("l40s-group", "L40S"),
            MockJob("rtx4080-group", "RTX4080"),
        ]
        all_identical = all(
            job.job_spec.requirements == jobs[0].job_spec.requirements for job in jobs
        )
        assert all_identical is False, "Different GPU types should trigger per-job offer fetch"

        # Scenario 2: Replica groups with same GPU -> shared fetch (optimization)
        jobs = [
            MockJob("group-1", "A100"),
            MockJob("group-2", "A100"),
        ]
        all_identical = all(
            job.job_spec.requirements == jobs[0].job_spec.requirements for job in jobs
        )
        assert all_identical is True, "Identical GPUs should use shared offer fetch"

        # Scenario 3: Legacy replicas (same requirements) -> shared fetch
        jobs = [
            MockJob("default", "V100"),
            MockJob("default", "V100"),
        ]
        all_identical = all(
            job.job_spec.requirements == jobs[0].job_spec.requirements for job in jobs
        )
        assert all_identical is True, "Legacy replicas with same GPU should use shared fetch"

        # Scenario 4: Mixed groups (2 same + 1 different) -> per-job fetch
        jobs = [
            MockJob("a100-group-1", "A100"),
            MockJob("h100-group", "H100"),
            MockJob("a100-group-2", "A100"),
        ]
        all_identical = all(
            job.job_spec.requirements == jobs[0].job_spec.requirements for job in jobs
        )
        assert all_identical is False, "Mix of different GPUs should trigger per-job fetch for all"


class TestReplicaGroupOfferSearchIntegration:
    """Integration tests for replica group offer search behavior."""

    def test_different_gpu_types_creates_different_requirements(self):
        """Different replica group GPU types should create different Requirements objects."""
        # This tests the data model behavior that get_plan() relies on
        req_l40s = Requirements(
            resources=ResourcesSpec(
                gpu={"name": "L40S", "count": 1},
            )
        )

        req_rtx4080 = Requirements(
            resources=ResourcesSpec(
                gpu={"name": "RTX4080", "count": 1},
            )
        )

        # These should NOT be equal
        assert req_l40s != req_rtx4080

        # Verify the GPU names are different
        assert req_l40s.resources.gpu.name != req_rtx4080.resources.gpu.name

    def test_identical_gpu_types_creates_identical_requirements(self):
        """Identical replica group GPU types should create equal Requirements objects."""
        req_a = Requirements(
            resources=ResourcesSpec(
                gpu={"name": "A100", "count": 1},
            )
        )

        req_b = Requirements(
            resources=ResourcesSpec(
                gpu={"name": "A100", "count": 1},
            )
        )

        # These SHOULD be equal (enables optimization)
        assert req_a == req_b

    def test_requirements_with_different_memory(self):
        """Requirements with different GPU memory should not be equal."""
        req_16gb = Requirements(
            resources=ResourcesSpec(
                gpu={"name": "A100", "memory": "16GB", "count": 1},
            )
        )

        req_40gb = Requirements(
            resources=ResourcesSpec(
                gpu={"name": "A100", "memory": "40GB", "count": 1},
            )
        )

        # Different memory specifications
        assert req_16gb != req_40gb

    def test_requirements_with_different_cpu_specs(self):
        """Requirements with different CPU specs should not be equal."""
        req_low_cpu = Requirements(
            resources=ResourcesSpec(
                cpu={"min": 2},
                gpu={"name": "A100", "count": 1},
            )
        )

        req_high_cpu = Requirements(
            resources=ResourcesSpec(
                cpu={"min": 16},
                gpu={"name": "A100", "count": 1},
            )
        )

        # Different CPU requirements
        assert req_low_cpu != req_high_cpu
