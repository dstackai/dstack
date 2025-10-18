"""Test CLI display of run plans with replica groups."""

from dstack._internal.cli.utils.run import print_run_plan
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.repos import LocalRunRepoData
from dstack._internal.core.models.resources import Range, ResourcesSpec
from dstack._internal.core.models.runs import (
    ApplyAction,
    InstanceOfferWithAvailability,
    JobPlan,
    JobSpec,
    Requirements,
    RunPlan,
    RunSpec,
)


def create_test_offer(
    backend: BackendType,
    gpu_name: str,
    price: float,
    region: str = "us-east",
    availability: InstanceAvailability = InstanceAvailability.AVAILABLE,
) -> InstanceOfferWithAvailability:
    """Helper to create test offers."""
    return InstanceOfferWithAvailability(
        backend=backend,
        instance=InstanceType(
            name=f"{gpu_name.lower()}-instance",
            resources=Resources(
                cpus=8,
                memory_mib=16384,
                gpus=[Gpu(name=gpu_name, memory_mib=40960)],
                spot=False,
            ),
        ),
        region=region,
        price=price,
        availability=availability,
    )


class TestReplicaGroupsDisplayInCLI:
    """Test that replica groups are properly displayed in CLI output."""

    def test_multiple_replica_groups_show_group_names(self, capsys):
        """CLI should prefix offers with group names when multiple job plans exist."""
        # Create a service with 2 replica groups
        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
            replica_groups=[
                {
                    "name": "l40s-group",
                    "replicas": "1",
                    "resources": {"gpu": {"name": "L40S", "count": 1}},
                },
                {
                    "name": "a100-group",
                    "replicas": "1",
                    "resources": {"gpu": {"name": "A100", "count": 1}},
                },
            ],
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            configuration_path=".dstack.yml",
            profile=Profile(backends=[BackendType.VASTAI]),
        )

        # Create job plans for each group
        l40s_offer = create_test_offer(BackendType.VASTAI, "L40S", 0.50)
        a100_offer = create_test_offer(BackendType.VASTAI, "A100", 1.20)

        job_plan_l40s = JobPlan(
            job_spec=JobSpec(
                replica_num=0,
                replica_group_name="l40s-group",
                job_num=0,
                job_name="test-job-0",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "L40S", "count": 1})
                ),
            ),
            offers=[l40s_offer],
            total_offers=1,
            max_price=0.50,
        )

        job_plan_a100 = JobPlan(
            job_spec=JobSpec(
                replica_num=1,
                replica_group_name="a100-group",
                job_num=1,
                job_name="test-job-1",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "A100", "count": 1})
                ),
            ),
            offers=[a100_offer],
            total_offers=1,
            max_price=1.20,
        )

        run_plan = RunPlan(
            project_name="test-project",
            user="test-user",
            run_spec=run_spec,
            effective_run_spec=run_spec,
            job_plans=[job_plan_l40s, job_plan_a100],
            current_resource=None,
            action=ApplyAction.CREATE,
        )

        # Print the plan
        print_run_plan(run_plan, max_offers=10, include_run_properties=True)

        # Capture output
        captured = capsys.readouterr()
        output = captured.out

        # Verify group names are in the output
        assert "l40s-group" in output, "l40s-group name should appear in output"
        assert "a100-group" in output, "a100-group name should appear in output"

        # Verify both GPU types are shown
        assert "L40S" in output or "l40s" in output.lower()
        assert "A100" in output or "a100" in output.lower()

    def test_single_job_plan_no_group_prefix(self, capsys):
        """CLI should NOT prefix offers when only one job plan exists (legacy)."""
        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
            replicas=Range[int](min=1, max=1),
            resources=ResourcesSpec(gpu={"name": "V100", "count": 1}),
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            configuration_path=".dstack.yml",
            profile=Profile(backends=[BackendType.AWS]),
        )

        v100_offer = create_test_offer(BackendType.AWS, "V100", 0.80)

        job_plan = JobPlan(
            job_spec=JobSpec(
                replica_num=0,
                replica_group_name="default",
                job_num=0,
                job_name="test-job-0",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "V100", "count": 1})
                ),
            ),
            offers=[v100_offer],
            total_offers=1,
            max_price=0.80,
        )

        run_plan = RunPlan(
            project_name="test-project",
            user="test-user",
            run_spec=run_spec,
            effective_run_spec=run_spec,
            job_plans=[job_plan],
            current_resource=None,
            action=ApplyAction.CREATE,
        )

        # Print the plan
        print_run_plan(run_plan, max_offers=10, include_run_properties=True)

        # Capture output
        captured = capsys.readouterr()
        output = captured.out

        # Verify NO group prefix (legacy mode)
        assert "default:" not in output, "Legacy mode should not show group prefix"
        # But should show backend normally
        assert "aws" in output.lower()

    def test_replica_groups_offers_sorted_by_price(self, capsys):
        """Offers from multiple groups should be sorted by price across all groups."""
        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
            replica_groups=[
                {
                    "name": "expensive-group",
                    "replicas": "1",
                    "resources": {"gpu": {"name": "H100", "count": 1}},
                },
                {
                    "name": "cheap-group",
                    "replicas": "1",
                    "resources": {"gpu": {"name": "T4", "count": 1}},
                },
            ],
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            configuration_path=".dstack.yml",
            profile=Profile(backends=[BackendType.AWS]),
        )

        # Expensive offer
        h100_offer = create_test_offer(BackendType.AWS, "H100", 3.00)
        # Cheap offer
        t4_offer = create_test_offer(BackendType.AWS, "T4", 0.30)

        job_plan_expensive = JobPlan(
            job_spec=JobSpec(
                replica_num=0,
                replica_group_name="expensive-group",
                job_num=0,
                job_name="test-job-0",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "H100", "count": 1})
                ),
            ),
            offers=[h100_offer],
            total_offers=1,
            max_price=3.00,
        )

        job_plan_cheap = JobPlan(
            job_spec=JobSpec(
                replica_num=1,
                replica_group_name="cheap-group",
                job_num=1,
                job_name="test-job-1",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(resources=ResourcesSpec(gpu={"name": "T4", "count": 1})),
            ),
            offers=[t4_offer],
            total_offers=1,
            max_price=0.30,
        )

        run_plan = RunPlan(
            project_name="test-project",
            user="test-user",
            run_spec=run_spec,
            effective_run_spec=run_spec,
            job_plans=[job_plan_expensive, job_plan_cheap],
            current_resource=None,
            action=ApplyAction.CREATE,
        )

        # Print the plan
        print_run_plan(run_plan, max_offers=10, include_run_properties=True)

        # Capture output
        captured = capsys.readouterr()
        output = captured.out

        # Split output to find the offers table (after the header section)
        lines = output.split("\n")

        # Find lines that contain both a number and a group name (these are offer rows)
        offer_rows = [
            line
            for line in lines
            if ("cheap-group:" in line or "expensive-group:" in line)
            and line.strip().startswith(("1", "2", "3"))
        ]

        # The first offer row should be cheap-group (lower price)
        assert len(offer_rows) >= 2, "Should have at least 2 offer rows"
        assert "cheap-group:" in offer_rows[0], (
            "First offer should be cheap-group (sorted by price)"
        )
        assert "expensive-group:" in offer_rows[1], "Second offer should be expensive-group"
        assert "$0.3" in output  # Price displayed as $0.3
        assert "$3" in output  # Price displayed as $3

    def test_replica_group_with_no_offers_shows_message(self, capsys):
        """Replica groups with no available offers should show a message."""
        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
            replica_groups=[
                {
                    "name": "available-group",
                    "replicas": "1",
                    "resources": {"gpu": {"name": "L40S", "count": 1}},
                },
                {
                    "name": "unavailable-group",
                    "replicas": "1",
                    "resources": {"gpu": {"name": "A100", "count": 1}},
                },
            ],
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            configuration_path=".dstack.yml",
            profile=Profile(backends=[BackendType.VASTAI]),
        )

        # One group has offers, another doesn't
        l40s_offer = create_test_offer(BackendType.VASTAI, "L40S", 0.50)

        job_plan_with_offers = JobPlan(
            job_spec=JobSpec(
                replica_num=0,
                replica_group_name="available-group",
                job_num=0,
                job_name="test-job-0",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "L40S", "count": 1})
                ),
            ),
            offers=[l40s_offer],
            total_offers=1,
            max_price=0.50,
        )

        job_plan_no_offers = JobPlan(
            job_spec=JobSpec(
                replica_num=1,
                replica_group_name="unavailable-group",
                job_num=1,
                job_name="test-job-1",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "A100", "count": 1})
                ),
            ),
            offers=[],  # No offers
            total_offers=0,
            max_price=0.0,
        )

        run_plan = RunPlan(
            project_name="test-project",
            user="test-user",
            run_spec=run_spec,
            effective_run_spec=run_spec,
            job_plans=[job_plan_with_offers, job_plan_no_offers],
            current_resource=None,
            action=ApplyAction.CREATE,
        )

        # Print the plan
        print_run_plan(run_plan, max_offers=10, include_run_properties=True)

        # Capture output
        captured = capsys.readouterr()
        output = captured.out

        # Verify available group shows offer
        assert "available-group:" in output
        assert "L40S" in output

        # Verify unavailable group shows the standard "no offers" message
        # (Message may be wrapped across lines in table display)
        assert "unavailable-group:" in output
        assert "No matching instance" in output
        assert "offers available" in output
        assert "Possible reasons:" in output
        assert "dstack.ai/docs" in output  # URL may be truncated in table

        # Verify unavailable group appears BEFORE available group (at top)
        unavailable_pos = output.find("unavailable-group:")
        available_pos = output.find("available-group:")
        assert unavailable_pos < available_pos, "Group with no offers should appear first"


class TestReplicaGroupsFairOfferDistribution:
    """Test that CLI displays offers from all replica groups fairly."""

    def test_all_groups_represented_in_display(self, capsys):
        """Test that offers from all replica groups are shown when max_offers is set."""
        # Create offers for three groups with different price ranges
        h100_offers = [
            create_test_offer(BackendType.AWS, "H100", 3.0, region="us-east"),
            create_test_offer(BackendType.AWS, "H100", 3.5, region="us-west"),
            create_test_offer(BackendType.GCP, "H100", 4.0, region="eu-west"),
        ]

        rtx5090_offers = [
            create_test_offer(BackendType.VASTAI, "RTX5090", 0.5, region="us"),
            create_test_offer(BackendType.VASTAI, "RTX5090", 0.6, region="eu"),
        ]

        a100_offers = [
            create_test_offer(BackendType.AWS, "A100", 2.0, region="us-east"),
            create_test_offer(BackendType.GCP, "A100", 2.2, region="eu-west"),
        ]

        # Create job plans for each group
        job_plan_h100 = JobPlan(
            job_spec=JobSpec(
                replica_num=0,
                replica_group_name="h100-group",
                job_num=0,
                job_name="test-job-0",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "H100", "count": 1})
                ),
            ),
            offers=h100_offers,
            total_offers=len(h100_offers),
            max_price=4.0,
        )

        job_plan_rtx5090 = JobPlan(
            job_spec=JobSpec(
                replica_num=1,
                replica_group_name="rtx5090-group",
                job_num=1,
                job_name="test-job-1",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "RTX5090", "count": 1})
                ),
            ),
            offers=rtx5090_offers,
            total_offers=len(rtx5090_offers),
            max_price=0.6,
        )

        job_plan_a100 = JobPlan(
            job_spec=JobSpec(
                replica_num=2,
                replica_group_name="a100-group",
                job_num=2,
                job_name="test-job-2",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "A100", "count": 1})
                ),
            ),
            offers=a100_offers,
            total_offers=len(a100_offers),
            max_price=2.2,
        )

        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            configuration_path=".dstack.yml",
            profile=Profile(backends=[BackendType.AWS]),
        )

        run_plan = RunPlan(
            project_name="test-project",
            user="test-user",
            run_spec=run_spec,
            effective_run_spec=run_spec,
            job_plans=[job_plan_h100, job_plan_rtx5090, job_plan_a100],
            current_resource=None,
            action=ApplyAction.CREATE,
        )

        # Print with max_offers=5 (should show at least 1 from each group)
        print_run_plan(run_plan, max_offers=5, include_run_properties=True)

        captured = capsys.readouterr()
        output = captured.out

        # Verify all three groups appear in the output
        assert "h100-group:" in output, "H100 group should be displayed"
        assert "rtx5090-group:" in output, "RTX5090 group should be displayed"
        assert "a100-group:" in output, "A100 group should be displayed"

        # Verify GPUs are shown
        assert "H100" in output
        assert "RTX5090" in output
        assert "A100" in output

    def test_fair_distribution_with_limited_slots(self, capsys):
        """Test that when max_offers is limited, all groups get fair representation."""
        # Group 1: Many cheap offers
        cheap_offers = [
            create_test_offer(BackendType.VASTAI, "RTX5090", 0.4 + i * 0.1, region="us")
            for i in range(10)
        ]

        # Group 2: Few expensive offers
        expensive_offers = [
            create_test_offer(BackendType.AWS, "H100", 3.0 + i * 0.5, region="us-east")
            for i in range(3)
        ]

        job_plan_cheap = JobPlan(
            job_spec=JobSpec(
                replica_num=0,
                replica_group_name="cheap-group",
                job_num=0,
                job_name="test-job-0",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "RTX5090", "count": 1})
                ),
            ),
            offers=cheap_offers,
            total_offers=len(cheap_offers),
            max_price=1.4,
        )

        job_plan_expensive = JobPlan(
            job_spec=JobSpec(
                replica_num=1,
                replica_group_name="expensive-group",
                job_num=1,
                job_name="test-job-1",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "H100", "count": 1})
                ),
            ),
            offers=expensive_offers,
            total_offers=len(expensive_offers),
            max_price=4.0,
        )

        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            configuration_path=".dstack.yml",
            profile=Profile(backends=[BackendType.VASTAI]),
        )

        run_plan = RunPlan(
            project_name="test-project",
            user="test-user",
            run_spec=run_spec,
            effective_run_spec=run_spec,
            job_plans=[job_plan_cheap, job_plan_expensive],
            current_resource=None,
            action=ApplyAction.CREATE,
        )

        # Print with max_offers=4 (should show at least 1 from each group)
        print_run_plan(run_plan, max_offers=4, include_run_properties=True)

        captured = capsys.readouterr()
        output = captured.out

        # Both groups should be represented
        assert "cheap-group:" in output
        assert "expensive-group:" in output

        # Count occurrences (rough check - both should appear)
        cheap_count = output.count("cheap-group:")
        expensive_count = output.count("expensive-group:")

        # Both should have at least one offer shown
        assert cheap_count >= 1, "Cheap group should have at least one offer"
        assert expensive_count >= 1, "Expensive group should have at least one offer"


class TestReplicaGroupsProfileOverridesDisplay:
    """Test that CLI correctly displays profile overrides for replica groups."""

    def test_shows_group_specific_spot_policy_and_regions(self, capsys):
        """Test that group-specific spot_policy, regions, backends are displayed."""

        from dstack._internal.core.models.backends.base import BackendType

        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
            replica_groups=[
                {
                    "name": "h100-group",
                    "replicas": "1",
                    "resources": {"gpu": {"name": "H100", "count": 1}},
                    "spot_policy": "spot",
                    "regions": ["us-east-1", "us-west-2"],
                    "backends": ["aws"],
                },
                {
                    "name": "rtx5090-group",
                    "replicas": "0..5",
                    "resources": {"gpu": {"name": "RTX5090", "count": 1}},
                    "spot_policy": "on-demand",
                    "regions": ["jp-japan"],
                    "backends": ["vastai", "runpod"],
                },
            ],
            scaling={"metric": "rps", "target": 10},
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            configuration_path=".dstack.yml",
            profile=Profile(backends=[BackendType.AWS]),
        )

        # Create job plans
        job_plan_h100 = JobPlan(
            job_spec=JobSpec(
                replica_num=0,
                replica_group_name="h100-group",
                job_num=0,
                job_name="test-job-0",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "H100", "count": 1})
                ),
            ),
            offers=[create_test_offer(BackendType.AWS, "H100", 3.0)],
            total_offers=1,
            max_price=3.0,
        )

        job_plan_rtx = JobPlan(
            job_spec=JobSpec(
                replica_num=1,
                replica_group_name="rtx5090-group",
                job_num=1,
                job_name="test-job-1",
                image_name="dstackai/base",
                commands=["echo test"],
                env={},
                working_dir="/workflow",
                requirements=Requirements(
                    resources=ResourcesSpec(gpu={"name": "RTX5090", "count": 1})
                ),
            ),
            offers=[create_test_offer(BackendType.VASTAI, "RTX5090", 0.5)],
            total_offers=1,
            max_price=0.5,
        )

        run_plan = RunPlan(
            project_name="test-project",
            user="test-user",
            run_spec=run_spec,
            effective_run_spec=run_spec,
            job_plans=[job_plan_h100, job_plan_rtx],
            current_resource=None,
            action=ApplyAction.CREATE,
        )

        # Print the plan
        print_run_plan(run_plan, max_offers=10, include_run_properties=True)

        # Capture output
        captured = capsys.readouterr()
        output = captured.out

        # Verify group-specific overrides are shown
        assert "h100-group" in output
        assert "spot=spot" in output  # H100 group's spot policy
        assert "regions=us-east-1,us-west-2" in output  # H100 group's regions
        assert "backends=aws" in output  # H100 group's backend

        assert "rtx5090-group" in output
        assert "spot=on-demand" in output  # RTX5090 group's spot policy
        assert "regions=jp-japan" in output  # RTX5090 group's region
        assert "backends=vastai,runpod" in output  # RTX5090 group's backends

        # Verify service-level "Spot policy" row is NOT shown (misleading with groups)
        lines = output.split("\n")
        spot_policy_lines = [line for line in lines if line.strip().startswith("Spot policy")]
        assert len(spot_policy_lines) == 0, (
            "Service-level 'Spot policy' should not be shown with replica_groups"
        )
