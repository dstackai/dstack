import re
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

import pytest
from rich.table import Table
from rich.text import Text

from dstack._internal.cli.utils.fleet import get_fleets_table
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import (
    Fleet,
    FleetConfiguration,
    FleetNodesSpec,
    FleetSpec,
    FleetStatus,
    InstanceGroupPlacement,
    SSHHostParams,
    SSHParams,
)
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    Instance,
    InstanceStatus,
    InstanceType,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.profiles import Profile, SpotPolicy
from dstack._internal.core.models.resources import GPUSpec, Range, ResourcesSpec


def _strip_rich_markup(text: str) -> str:
    return re.sub(r"\[[^\]]*\]([^\[]*)\[/[^\]]*\]", r"\1", text)


def get_table_cells(table: Table) -> list[dict[str, str]]:
    rows = []

    if not table.columns:
        return rows

    num_rows = len(table.columns[0]._cells)

    for row_idx in range(num_rows):
        row = {}
        for col in table.columns:
            col_name = str(col.header)
            if row_idx < len(col._cells):
                cell_value = col._cells[row_idx]
                if isinstance(cell_value, Text):
                    row[col_name] = cell_value.plain
                else:
                    text = str(cell_value)
                    row[col_name] = _strip_rich_markup(text)
            else:
                row[col_name] = ""
        rows.append(row)

    return rows


def get_table_cell_style(table: Table, column_name: str, row_idx: int = 0) -> Optional[str]:
    for col in table.columns:
        if str(col.header) == column_name:
            if row_idx < len(col._cells):
                cell_value = col._cells[row_idx]
                if isinstance(cell_value, Text):
                    return str(cell_value.style) if cell_value.style else None
                text = str(cell_value)
                match = re.search(r"\[([^\]]+)\][^\[]*\[/\]", text)
                if match:
                    return match.group(1)
            return None
    return None


def create_test_instance(
    instance_num: int = 0,
    backend: BackendType = BackendType.AWS,
    region: str = "us-east-1",
    status: InstanceStatus = InstanceStatus.IDLE,
    price: Optional[float] = 0.50,
    spot: bool = False,
    gpu_name: Optional[str] = None,
    gpu_count: int = 0,
    gpu_memory_mib: int = 0,
) -> Instance:
    gpus = []
    if gpu_count > 0 and gpu_name:
        gpus = [Gpu(name=gpu_name, memory_mib=gpu_memory_mib)] * gpu_count

    resources = Resources(
        cpus=4,
        memory_mib=16384,
        gpus=gpus,
        spot=spot,
        disk=Disk(size_mib=102400),
    )
    instance_type = InstanceType(name="test-instance", resources=resources)

    return Instance(
        id=uuid4(),
        project_name="test-project",
        name=f"instance-{instance_num}",
        instance_num=instance_num,
        backend=backend,
        region=region,
        status=status,
        price=price,
        instance_type=instance_type,
        created=datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    )


def create_backend_fleet(
    name: str = "test-fleet",
    nodes_min: int = 0,
    nodes_max: int = 2,
    backends: Optional[List[BackendType]] = None,
    spot_policy: SpotPolicy = SpotPolicy.AUTO,
    max_price: Optional[float] = None,
    placement: Optional[InstanceGroupPlacement] = None,
    gpu_count_min: int = 0,
    gpu_count_max: int = 0,
    instances: Optional[List[Instance]] = None,
    status: FleetStatus = FleetStatus.ACTIVE,
) -> Fleet:
    nodes = FleetNodesSpec(min=nodes_min, target=nodes_min, max=nodes_max)

    gpu_spec = None
    if gpu_count_max > 0:
        gpu_spec = GPUSpec(count=Range[int](min=gpu_count_min, max=gpu_count_max))

    resources = ResourcesSpec(gpu=gpu_spec) if gpu_spec else ResourcesSpec()

    config = FleetConfiguration(
        name=name,
        nodes=nodes,
        backends=backends,
        placement=placement,
        resources=resources,
    )

    profile = Profile(name="default", spot_policy=spot_policy, max_price=max_price)

    spec = FleetSpec(
        configuration=config,
        configuration_path="fleet.dstack.yml",
        profile=profile,
    )

    return Fleet(
        id=uuid4(),
        name=name,
        project_name="test-project",
        spec=spec,
        created_at=datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        status=status,
        instances=instances or [],
    )


def create_ssh_fleet(
    name: str = "ssh-fleet",
    hosts: Optional[List[str]] = None,
    placement: Optional[InstanceGroupPlacement] = None,
    instances: Optional[List[Instance]] = None,
    status: FleetStatus = FleetStatus.ACTIVE,
) -> Fleet:
    if hosts is None:
        hosts = ["10.0.0.1", "10.0.0.2"]

    ssh_key = SSHKey(public="ssh-rsa AAAA...", private="-----BEGIN PRIVATE KEY-----\n...")
    ssh_config = SSHParams(
        user="ubuntu",
        ssh_key=ssh_key,
        hosts=[SSHHostParams(hostname=h) for h in hosts],
        network=None,
    )

    config = FleetConfiguration(
        name=name,
        ssh_config=ssh_config,
        placement=placement,
    )

    spec = FleetSpec(
        configuration=config,
        configuration_path="fleet.dstack.yml",
        profile=Profile(name="default"),
    )

    return Fleet(
        id=uuid4(),
        name=name,
        project_name="test-project",
        spec=spec,
        created_at=datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        status=status,
        instances=instances or [],
    )


class TestGetFleetsTable:
    def test_backend_fleet_without_verbose(self):
        instance = create_test_instance(
            instance_num=0,
            backend=BackendType.AWS,
            region="us-east-1",
            status=InstanceStatus.IDLE,
            price=0.50,
            spot=True,
        )
        fleet = create_backend_fleet(
            name="my-cloud",
            nodes_min=0,
            nodes_max=4,
            backends=[BackendType.AWS],
            spot_policy=SpotPolicy.AUTO,
            instances=[instance],
        )

        table = get_fleets_table([fleet], verbose=False)
        cells = get_table_cells(table)

        assert len(cells) == 2  # 1 fleet row + 1 instance row

        fleet_row = cells[0]
        assert fleet_row["NAME"] == "my-cloud"
        assert fleet_row["NODES"] == "0..4"
        assert fleet_row["BACKEND"] == "aws"
        assert fleet_row["SPOT"] == "auto"
        assert fleet_row["PRICE"] == "-"  # no max_price set
        assert fleet_row["STATUS"] == "active"

        instance_row = cells[1]
        assert "instance=0" in instance_row["NAME"]
        assert instance_row["BACKEND"] == "aws (us-east-1)"
        assert instance_row["SPOT"] == "spot"
        assert instance_row["PRICE"] == "$0.5"
        assert instance_row["STATUS"] == "idle"

    def test_backend_fleet_with_verbose(self):
        instance = create_test_instance(
            instance_num=0,
            backend=BackendType.GCP,
            region="us-west4",
            status=InstanceStatus.BUSY,
            price=1.25,
            spot=False,
        )
        fleet = create_backend_fleet(
            name="my-cloud",
            nodes_min=1,
            nodes_max=1,
            backends=[BackendType.GCP],
            spot_policy=SpotPolicy.ONDEMAND,
            max_price=2.0,
            placement=InstanceGroupPlacement.CLUSTER,
            instances=[instance],
        )

        table = get_fleets_table([fleet], verbose=True)
        cells = get_table_cells(table)

        assert len(cells) == 2

        fleet_row = cells[0]
        assert fleet_row["NAME"] == "my-cloud"
        assert fleet_row["NODES"] == "1 (cluster)"
        assert fleet_row["BACKEND"] == "gcp"
        assert fleet_row["SPOT"] == "on-demand"
        assert fleet_row["PRICE"] == "$0..$2"
        assert fleet_row["STATUS"] == "active"

        instance_row = cells[1]
        assert "instance=0" in instance_row["NAME"]
        assert instance_row["BACKEND"] == "gcp (us-west4)"
        assert instance_row["SPOT"] == "on-demand"
        assert instance_row["PRICE"] == "$1.25"

    def test_ssh_fleet_without_verbose(self):
        instance1 = create_test_instance(
            instance_num=0,
            backend=BackendType.REMOTE,
            region="",
            status=InstanceStatus.IDLE,
            price=None,
            spot=False,
            gpu_name="L4",
            gpu_count=1,
            gpu_memory_mib=24576,
        )
        instance2 = create_test_instance(
            instance_num=1,
            backend=BackendType.REMOTE,
            region="",
            status=InstanceStatus.BUSY,
            price=None,
            spot=False,
            gpu_name="L4",
            gpu_count=1,
            gpu_memory_mib=24576,
        )
        fleet = create_ssh_fleet(
            name="my-ssh",
            hosts=["10.0.0.1", "10.0.0.2"],
            instances=[instance1, instance2],
        )

        table = get_fleets_table([fleet], verbose=False)
        cells = get_table_cells(table)

        assert len(cells) == 3  # 1 fleet row + 2 instance rows

        fleet_row = cells[0]
        assert fleet_row["NAME"] == "my-ssh"
        assert fleet_row["NODES"] == "2"
        assert fleet_row["BACKEND"] == "ssh"
        assert fleet_row["SPOT"] == "-"
        assert fleet_row["PRICE"] == "-"
        assert fleet_row["STATUS"] == "active"

        for i, instance_row in enumerate(cells[1:], start=0):
            assert f"instance={i}" in instance_row["NAME"]
            assert instance_row["BACKEND"] == "ssh"
            assert instance_row["SPOT"] == "-"
            assert instance_row["PRICE"] == "-"

    def test_ssh_fleet_with_verbose(self):
        instance = create_test_instance(
            instance_num=0,
            backend=BackendType.REMOTE,
            region="",
            status=InstanceStatus.IDLE,
            price=None,
            spot=False,
        )
        fleet = create_ssh_fleet(
            name="my-ssh",
            hosts=["10.0.0.1"],
            placement=InstanceGroupPlacement.CLUSTER,
            instances=[instance],
        )

        table = get_fleets_table([fleet], verbose=True)
        cells = get_table_cells(table)

        assert len(cells) == 2

        fleet_row = cells[0]
        assert fleet_row["NAME"] == "my-ssh"
        assert fleet_row["NODES"] == "1 (cluster)"
        assert fleet_row["BACKEND"] == "ssh"
        assert fleet_row["SPOT"] == "-"
        assert fleet_row["PRICE"] == "-"

        instance_row = cells[1]
        assert "instance=0" in instance_row["NAME"]
        assert instance_row["BACKEND"] == "ssh"
        assert instance_row["SPOT"] == "-"
        assert instance_row["PRICE"] == "-"

    def test_mixed_fleets(self):
        backend_instance = create_test_instance(
            instance_num=0,
            backend=BackendType.AWS,
            region="us-east-1",
            status=InstanceStatus.BUSY,
            price=0.75,
            spot=True,
        )
        backend_fleet = create_backend_fleet(
            name="cloud-fleet",
            nodes_min=0,
            nodes_max=2,
            backends=[BackendType.AWS],
            spot_policy=SpotPolicy.SPOT,
            instances=[backend_instance],
        )

        ssh_instance = create_test_instance(
            instance_num=0,
            backend=BackendType.REMOTE,
            region="",
            status=InstanceStatus.IDLE,
            price=None,
            spot=False,
        )
        ssh_fleet = create_ssh_fleet(
            name="ssh-fleet",
            hosts=["10.0.0.1"],
            instances=[ssh_instance],
        )

        table = get_fleets_table([backend_fleet, ssh_fleet], verbose=False)
        cells = get_table_cells(table)

        assert len(cells) == 4  # 2 fleet rows + 2 instance rows

        assert cells[0]["NAME"] == "cloud-fleet"
        assert cells[0]["NODES"] == "0..2"
        assert cells[0]["BACKEND"] == "aws"
        assert cells[0]["SPOT"] == "spot"

        assert "instance=0" in cells[1]["NAME"]
        assert cells[1]["SPOT"] == "spot"
        assert cells[1]["PRICE"] == "$0.75"

        assert cells[2]["NAME"] == "ssh-fleet"
        assert cells[2]["NODES"] == "1"
        assert cells[2]["BACKEND"] == "ssh"
        assert cells[2]["SPOT"] == "-"
        assert cells[2]["PRICE"] == "-"

        assert "instance=0" in cells[3]["NAME"]
        assert cells[3]["SPOT"] == "-"
        assert cells[3]["PRICE"] == "-"

    def test_fleet_status_colors(self):
        # Add instances to avoid placeholder rows affecting row indices
        active_instance = create_test_instance(instance_num=0, status=InstanceStatus.IDLE)
        active_fleet = create_backend_fleet(
            name="active", status=FleetStatus.ACTIVE, instances=[active_instance]
        )

        terminating_instance = create_test_instance(instance_num=0, status=InstanceStatus.TERMINATING)
        terminating_fleet = create_backend_fleet(
            name="terminating", status=FleetStatus.TERMINATING, instances=[terminating_instance]
        )

        table = get_fleets_table([active_fleet, terminating_fleet], verbose=False)

        active_style = get_table_cell_style(table, "STATUS", 0)
        assert active_style == "bold white"

        # Row 2 (after active fleet's instance)
        terminating_style = get_table_cell_style(table, "STATUS", 2)
        assert terminating_style == "bold deep_sky_blue1"

    def test_instance_status_colors(self):
        idle_instance = create_test_instance(instance_num=0, status=InstanceStatus.IDLE)
        busy_instance = create_test_instance(instance_num=1, status=InstanceStatus.BUSY)

        fleet = create_backend_fleet(
            name="test",
            instances=[idle_instance, busy_instance],
        )

        table = get_fleets_table([fleet], verbose=False)

        idle_style = get_table_cell_style(table, "STATUS", 1)
        assert idle_style == "bold sea_green3"

        busy_style = get_table_cell_style(table, "STATUS", 2)
        assert busy_style == "bold white"

    def test_empty_fleet(self):
        fleet = create_backend_fleet(name="empty-fleet", instances=[])

        table = get_fleets_table([fleet], verbose=False)
        cells = get_table_cells(table)

        assert len(cells) == 1
        assert cells[0]["NAME"] == "empty-fleet"

    def test_fleet_with_max_price(self):
        fleet = create_backend_fleet(
            name="priced-fleet",
            max_price=5.0,
        )

        table = get_fleets_table([fleet], verbose=False)
        cells = get_table_cells(table)

        assert cells[0]["PRICE"] == "$0..$5"

    def test_fleet_with_multiple_backends(self):
        fleet = create_backend_fleet(
            name="multi-backend",
            backends=[BackendType.AWS, BackendType.GCP, BackendType.AZURE],
        )

        table = get_fleets_table([fleet], verbose=False)
        cells = get_table_cells(table)

        assert cells[0]["BACKEND"] == "aws, gcp, azure"

    def test_fleet_with_any_backend(self):
        fleet = create_backend_fleet(
            name="any-backend",
            backends=None,
        )

        table = get_fleets_table([fleet], verbose=False)
        cells = get_table_cells(table)

        assert cells[0]["BACKEND"] == "*"
