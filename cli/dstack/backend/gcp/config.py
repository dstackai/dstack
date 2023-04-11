import json
import os
from argparse import Namespace
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml
from google.cloud import compute_v1, exceptions, storage
from google.oauth2 import service_account
from rich.prompt import Confirm, Prompt
from rich_argparse import RichHelpFormatter

from dstack.cli.common import ask_choice, console, is_termios_available
from dstack.core.config import BackendConfig, Configurator, get_config_path
from dstack.core.error import ConfigError, HubConfigError
from dstack.hub.models import (
    GCPProjectValues,
    GCPVPCSubnetProjectElement,
    GCPVPCSubnetProjectElementValue,
    ProjectElement,
    ProjectElementValue,
)

DEFAULT_GEOGRAPHIC_AREA = "North America"

GCP_LOCATIONS = [
    {
        "name": "North America",
        "regions": [
            "northamerica-northeast1",
            "northamerica-northeast2",
            "us-central1",
            "us-east1",
            "us-east4",
            "us-east5",
            "us-south1",
            "us-west1",
            "us-west2",
            "us-west3",
            "us-west4",
        ],
        "default_region": "us-west1",
        "default_zone": "us-west1-b",
    },
    {
        "name": "South America",
        "regions": [
            "southamerica-east1",
            "southamerica-west1",
        ],
        "default_region": "southamerica-east1",
        "default_zone": "southamerica-east1-b",
    },
    {
        "name": "Europe",
        "regions": [
            "europe-central2",
            "europe-north1",
            "europe-southwest1",
            "europe-west1",
            "europe-west2",
            "europe-west3",
            "europe-west4",
            "europe-west6",
            "europe-west8",
            "europe-west9",
        ],
        "default_region": "europe-west4",
        "default_zone": "europe-west4-a",
    },
    {
        "name": "Asia",
        "regions": [
            "asia-east1",
            "asia-east2",
            "asia-northeast1",
            "asia-northeast2",
            "asia-northeast3",
            "asia-south1",
            "asia-south2",
            "asia-southeast1",
            "asia-southeast2",
        ],
        "default_region": "asia-southeast1",
        "default_zone": "asia-southeast1-b",
    },
    {
        "name": "Middle East",
        "regions": [
            "me-west1",
        ],
        "default_region": "me-west1",
        "default_zone": "me-west1-b",
    },
    {
        "name": "Australia",
        "regions": [
            "australia-southeast1",
            "australia-southeast2",
        ],
        "default_region": "australia-southeast1",
        "default_zone": "australia-southeast1-c",
    },
]


class GCPConfig(BackendConfig):
    def __init__(
        self,
        project_id: str,
        region: str,
        zone: str,
        bucket_name: str,
        vpc: str,
        subnet: str,
        credentials_file: Optional[str] = None,
        credentials: Optional[Dict] = None,
    ):
        self.project_id = project_id
        self.region = region
        self.zone = zone
        self.bucket_name = bucket_name
        self.vpc = vpc
        self.subnet = subnet
        self.credentials_file = credentials_file
        self.credentials = credentials

    def serialize(self) -> Dict:
        res = {
            "backend": "gcp",
            "project": self.project_id,
            "region": self.region,
            "zone": self.zone,
            "bucket": self.bucket_name,
            "vpc": self.vpc,
            "subnet": self.subnet,
        }
        if self.credentials_file is not None:
            res["credentials_file"] = self.credentials_file
        return res

    def serialize_yaml(self) -> str:
        return yaml.dump(self.serialize())

    @classmethod
    def deserialize(cls, config_data: Dict) -> Optional["GCPConfig"]:
        if config_data.get("backend") != "gcp":
            raise ConfigError(f"Not a GCP config")
        try:
            project_id = config_data["project"]
            region = config_data["region"]
            zone = config_data["zone"]
            bucket_name = config_data["bucket"]
            vpc = config_data["vpc"]
            subnet = config_data["subnet"]
        except KeyError:
            raise ConfigError("Cannot load config")

        return cls(
            project_id=project_id,
            region=region,
            zone=zone,
            bucket_name=bucket_name,
            vpc=vpc,
            subnet=subnet,
            credentials_file=config_data.get("credentials_file"),
            credentials=config_data.get("credentials"),
        )

    @classmethod
    def deserialize_yaml(cls, yaml_content: str) -> "GCPConfig":
        content = yaml.load(yaml_content, yaml.FullLoader)
        if content is None:
            raise ConfigError("Cannot load config")
        return cls.deserialize(content)

    @classmethod
    def load(cls, path: Path = get_config_path()) -> "GCPConfig":
        if not path.exists():
            raise ConfigError("No config found")
        with open(path) as f:
            return GCPConfig.deserialize_yaml(f.read())

    def save(self, path: Path = get_config_path()):
        with open(path, "w+") as f:
            f.write(self.serialize_yaml())


class GCPConfigurator(Configurator):
    @property
    def name(self):
        return "gcp"

    def get_config_from_hub_config_data(self, config_data: Dict, auth_data: Dict) -> BackendConfig:
        credentials = json.loads(auth_data["credentials"])
        data = {
            "backend": "gcp",
            "credentials": credentials,
            "project": credentials["project_id"],
            "region": config_data["region"],
            "zone": config_data["zone"],
            "bucket": config_data["bucket_name"],
            "vpc": config_data["vpc"],
            "subnet": config_data["subnet"],
        }
        return GCPConfig.deserialize(data)

    def register_parser(self, parser):
        gcp_parser = parser.add_parser("gcp", help="", formatter_class=RichHelpFormatter)
        gcp_parser.add_argument("--bucket", type=str, help="", required=True)
        gcp_parser.add_argument("--project", type=str, help="", required=True)
        gcp_parser.add_argument("--region", type=str, help="", required=True)
        gcp_parser.add_argument("--zone", type=str, help="", required=True)
        gcp_parser.add_argument("--vpc", type=str, help="", required=True)
        gcp_parser.add_argument("--subnet", type=str, help="", required=True)
        gcp_parser.set_defaults(func=self._command)

    def _command(self, args: Namespace):
        config = GCPConfig(
            project_id=args.project,
            region=args.region,
            zone=args.zone,
            bucket_name=args.bucket,
            subnet=args.subnet,
            vpc=args.vpc,
        )
        config.save()
        print(f"[grey58]OK[/]")

    def configure_hub(self, config_data: Dict) -> GCPProjectValues:
        try:
            service_account_info = json.loads(config_data.get("credentials"))
            self.credentials = service_account.Credentials.from_service_account_info(
                info=service_account_info
            )
            storage_client = storage.Client(credentials=self.credentials)
            storage_client.list_buckets(max_results=1)
        except Exception:
            raise HubConfigError(
                "Credentials are not valid", code="invalid_credentials", fields=["credentials"]
            )
        project_values = GCPProjectValues()
        project_values.area = self._get_hub_geographic_area(config_data.get("area"))
        location = self._get_location(project_values.area.selected)
        project_values.region, regions = self._get_hub_region(
            location=location,
            default_region=config_data.get("region"),
        )
        project_values.zone = self._get_hub_zone(
            location=location,
            region=regions.get(project_values.region.selected),
            default_zone=config_data.get("zone"),
        )
        project_values.bucket_name = self._get_hub_buckets(
            region=project_values.region.selected,
            default_bucket=config_data.get("bucket_name"),
        )
        project_values.vpc_subnet = self._get_hub_vpc_subnet(
            region=project_values.region.selected,
            default_vpc=config_data.get("vpc"),
            default_subnet=config_data.get("subnet"),
        )
        return project_values

    def _get_hub_geographic_area(self, default_area: Optional[str]) -> ProjectElement:
        area_names = sorted([l["name"] for l in GCP_LOCATIONS])
        if default_area is None:
            default_area = DEFAULT_GEOGRAPHIC_AREA
        if default_area not in area_names:
            raise HubConfigError(f"Invalid GCP area {default_area}")
        element = ProjectElement(selected=default_area)
        for area_name in area_names:
            element.values.append(ProjectElementValue(value=area_name, label=area_name))
        return element

    def _get_hub_region(
        self, location: Dict, default_region: Optional[str]
    ) -> Tuple[ProjectElement, Dict]:
        regions_client = compute_v1.RegionsClient(credentials=self.credentials)
        regions = regions_client.list(project=self.credentials.project_id)
        region_names = sorted(
            [r.name for r in regions if r.name in location["regions"]],
            key=lambda name: (name != location["default_region"], name),
        )
        if default_region is None:
            default_region = region_names[0]
        if default_region not in region_names:
            raise HubConfigError(f"Invalid GCP region {default_region} in area {location['name']}")
        element = ProjectElement(selected=default_region)
        for region_name in region_names:
            element.values.append(ProjectElementValue(value=region_name, label=region_name))
        return element, {r.name: r for r in regions}

    def _get_hub_zone(
        self, location: Dict, region: compute_v1.Region, default_zone: Optional[str]
    ) -> ProjectElement:
        zone_names = sorted(
            [self._get_resource_name(z) for z in region.zones],
            key=lambda name: (name != location["default_zone"], name),
        )
        if default_zone is None:
            default_zone = zone_names[0]
        if default_zone not in zone_names:
            raise HubConfigError(f"Invalid GCP zone {default_zone} in region {region.name}")
        element = ProjectElement(selected=default_zone)
        for zone_name in zone_names:
            element.values.append(ProjectElementValue(value=zone_name, label=zone_name))
        return element

    def _get_hub_buckets(
        self, region: str, default_bucket: Optional[str] = None
    ) -> ProjectElement:
        storage_client = storage.Client(credentials=self.credentials)
        buckets = storage_client.list_buckets()
        bucket_names = [bucket.name for bucket in buckets if bucket.location.lower() == region]
        if default_bucket is not None and default_bucket not in bucket_names:
            raise HubConfigError(
                f"Invalid bucket {default_bucket} for region {region}",
                code="invalid_bucket",
                fields=["bucket_name"],
            )
        element = ProjectElement(selected=default_bucket)
        for bucket_name in bucket_names:
            element.values.append(ProjectElementValue(value=bucket_name, label=bucket_name))
        return element

    def _get_hub_vpc_subnet(
        self,
        region: str,
        default_vpc: Optional[str],
        default_subnet: Optional[str],
    ) -> GCPVPCSubnetProjectElement:
        if default_vpc is None:
            default_vpc = "default"
        if default_subnet is None:
            default_subnet = "default"
        no_preference_vpc_subnet = ("default", "default")
        networks_client = compute_v1.NetworksClient(credentials=self.credentials)
        networks = networks_client.list(project=self.credentials.project_id)
        vpc_subnet_list = []
        for network in networks:
            for subnet in network.subnetworks:
                subnet_region = self._get_subnet_region(subnet)
                if subnet_region != region:
                    continue
                vpc_subnet_list.append((network.name, self._get_subnet_name(subnet)))
        if (default_vpc, default_subnet) not in vpc_subnet_list:
            raise HubConfigError(f"Invalid VPC subnet {default_vpc, default_subnet}")
        if (default_vpc, default_subnet) != no_preference_vpc_subnet:
            selected = f"{default_subnet} ({default_vpc})"
        else:
            selected = f"No preference (default)"
        vpc_subnet_list = sorted(vpc_subnet_list, key=lambda t: t != no_preference_vpc_subnet)
        element = GCPVPCSubnetProjectElement(selected=selected)
        for vpc, subnet in vpc_subnet_list:
            element.values.append(
                GCPVPCSubnetProjectElementValue(
                    vpc=vpc,
                    subnet=subnet,
                    label=f"{subnet} ({vpc})"
                    if (subnet, vpc) != no_preference_vpc_subnet
                    else f"No preference (default)",
                )
            )
        return element

    def configure_cli(self):
        credentials_file = None
        region = None
        zone = None
        bucket_name = None
        vpc = None
        subnet = None

        try:
            config = GCPConfig.load()
        except ConfigError:
            config = None

        if config is not None:
            credentials_file = config.credentials_file
            region = config.region
            zone = config.zone
            bucket_name = config.bucket_name
            vpc = config.vpc
            subnet = config.subnet

        self.credentials_file = self._ask_credentials_file(credentials_file)

        self.credentials = self._get_credentials(self.credentials_file)
        self.project_id = self.credentials.project_id

        default_area = self._get_region_geographic_area(region)
        area = self._ask_geographic_area(default_area)
        location = self._get_location(area)
        region = self._ask_region(location, region)
        self.region = region.name
        self.zone = self._ask_zone(location, region, zone)

        self.bucket_name = self._ask_bucket(bucket_name)
        self.vpc, self.subnet = self._ask_vpc_subnet(vpc, subnet)

        config = GCPConfig(
            project_id=self.project_id,
            region=self.region,
            zone=self.zone,
            bucket_name=self.bucket_name,
            vpc=self.vpc,
            subnet=self.subnet,
            credentials_file=self.credentials_file,
        )
        config.save()
        console.print(f"[grey58]OK[/]")

    def _ask_credentials_file(self, default_credentials_file: Optional[str]) -> str:
        if default_credentials_file is None:
            default_credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        credentials_file = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter path to credentials file[/bold]",
            default=default_credentials_file,
        )
        if credentials_file is not None:
            credentials_file = os.path.expanduser(credentials_file)
        if not credentials_file or self._get_credentials(credentials_file) is None:
            return self._ask_credentials_file(default_credentials_file)
        return credentials_file

    def _get_credentials(self, credentials_file: str) -> Optional[service_account.Credentials]:
        try:
            credentials = service_account.Credentials.from_service_account_file(credentials_file)
            storage_client = storage.Client(credentials=credentials)
            storage_client.list_buckets(max_results=1)
        except Exception as e:
            console.print(
                f"[red bold]✗[/red bold] Error while checking GCP credentials:\n{e}",
            )
            return None
        return credentials

    def _ask_geographic_area(self, default_area: Optional[str]) -> str:
        if default_area is None:
            default_area = DEFAULT_GEOGRAPHIC_AREA
        area_names = sorted([l["name"] for l in GCP_LOCATIONS])
        area_name = ask_choice(
            "Choose GCP geographic area",
            area_names,
            area_names,
            default_area,
        )
        return area_name

    def _ask_region(self, location: Dict, default_region: Optional[str]) -> compute_v1.Region:
        regions_client = compute_v1.RegionsClient(credentials=self.credentials)
        list_regions_request = compute_v1.ListRegionsRequest(project=self.project_id)
        regions = regions_client.list(list_regions_request)
        region_names = sorted(
            [r.name for r in regions if r.name in location["regions"]],
            key=lambda name: (name != location["default_region"], name),
        )
        if default_region is None:
            default_region = region_names[0]
        region_name = ask_choice(
            "Choose GCP region",
            region_names,
            region_names,
            default_region,
        )
        return {r.name: r for r in regions}[region_name]

    def _ask_zone(
        self, location: Dict, region: compute_v1.Region, default_zone: Optional[str]
    ) -> str:
        zone_names = sorted(
            [self._get_resource_name(z) for z in region.zones],
            key=lambda name: (name != location["default_zone"], name),
        )
        if default_zone not in zone_names:
            default_zone = zone_names[0]
        zone = ask_choice(
            "Choose GCP zone",
            zone_names,
            zone_names,
            default_zone,
        )
        return zone

    def _ask_bucket(self, default_bucket: Optional[str]) -> str:
        if default_bucket is None:
            default_bucket = f"dstack-{self.project_id}-{self.region}"
        if is_termios_available:
            from simple_term_menu import TerminalMenu

            console.print(
                "[sea_green3 bold]?[/sea_green3 bold] [bold]Choose storage bucket[/bold] "
                "[gray46]Use arrows to move, type to filter[/gray46]"
            )
            bucket_options = [f"Default [{default_bucket}]", "Custom..."]
            bucket_menu = TerminalMenu(
                bucket_options,
                menu_cursor_style=["fg_red", "bold"],
                menu_highlight_style=["fg_red", "bold"],
                search_highlight_style=["fg_purple"],
                raise_error_on_interrupt=True,
            )
            bucket_index = bucket_menu.show()
            bucket_title = bucket_options[bucket_index].replace("[", "\\[")
            console.print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{bucket_title}[/grey74]")
        else:
            bucket_index = 1
        if bucket_index == 1:
            return self._ask_bucket_name(default_bucket)
        if self._validate_bucket(default_bucket):
            return default_bucket
        return self._ask_bucket_name(default_bucket)

    def _ask_bucket_name(self, default_bucket: Optional[str]) -> str:
        bucket_name = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter bucket name[/bold]",
            default=default_bucket,
        )
        if self._validate_bucket(bucket_name):
            return bucket_name
        return self._ask_bucket_name(default_bucket)

    def _validate_bucket(self, bucket_name: str) -> bool:
        storage_client = storage.Client(project=self.project_id, credentials=self.credentials)
        try:
            bucket = storage_client.get_bucket(bucket_name)
        except (ValueError, exceptions.BadRequest) as e:
            console.print(
                "[red bold]✗[/red bold] Bucket name is not valid."
                " See bucket naming rules: https://cloud.google.com/storage/docs/buckets"
            )
            return False
        except exceptions.NotFound:
            if Confirm.ask(
                f"[sea_green3 bold]?[/sea_green3 bold] "
                f"[red bold]The bucket doesn't exist. Create it?[/red bold]",
                default="y",
            ):
                storage_client.create_bucket(bucket_name, location=self.region)
                return True
            else:
                return False

        if bucket.location.lower() not in [
            self.region,
            self._get_zone_multi_region_location(self.zone),
        ]:
            console.print(
                f"[red bold]✗[/red bold] Bucket location is '{bucket.location.lower()}',"
                f" but you chose '{self.region}' as region."
                f" Please use a bucket located in '{self.region}'."
            )
            return False

        return True

    def _ask_vpc_subnet(
        self, default_vpc: Optional[str], default_subnet: Optional[str]
    ) -> Tuple[str, str]:
        no_preference_vpc_subnet = ("default", "default")
        if default_vpc is None or default_subnet is None:
            default_vpc, default_subnet = no_preference_vpc_subnet
        networks_client = compute_v1.NetworksClient(credentials=self.credentials)
        list_networks_request = compute_v1.ListNetworksRequest(project=self.project_id)
        networks = networks_client.list(list_networks_request)
        subnets = []
        for network in networks:
            for subnet in network.subnetworks:
                subnet_region = self._get_subnet_region(subnet)
                if subnet_region != self.region:
                    continue
                subnets.append(
                    {
                        "vpc": network.name,
                        "subnet": self._get_subnet_name(subnet),
                    }
                )
        vpc_subnets = sorted(
            [(s["vpc"], s["subnet"]) for s in subnets], key=lambda t: t != no_preference_vpc_subnet
        )
        vpc_subnet_values = [f"{t[0]},{t[1]}" for t in vpc_subnets]
        vpc_subnet_labels = [
            f"{t[1]} [{t[0]}]" if t != no_preference_vpc_subnet else "Default [no preference]"
            for t in vpc_subnets
        ]
        vpc_subnet = ask_choice(
            "Choose VPC subnet",
            vpc_subnet_labels,
            vpc_subnet_values,
            f"{default_vpc},{default_subnet}",
        )
        vpc, subnet = vpc_subnet.split(",")
        return vpc, subnet

    def _get_resource_name(self, resource_path: str) -> str:
        return resource_path.rsplit(sep="/", maxsplit=1)[1]

    def _get_region_geographic_area(self, region: Optional[str]) -> Optional[str]:
        if region is None:
            return None
        for location in GCP_LOCATIONS:
            if region in location["regions"]:
                return location["name"]
        return None

    def _get_location(self, area: str) -> Optional[Dict]:
        for location in GCP_LOCATIONS:
            if location["name"] == area:
                return location
        return None

    def _get_zone_multi_region_location(self, zone: str) -> str:
        if zone.startswith("asia"):
            return "ASIA"
        if zone.startswith("eu"):
            return "EU"
        return "US"

    def _get_subnet_region(self, subnet_resource: str) -> str:
        return subnet_resource.rsplit(sep="/", maxsplit=3)[1]

    def _get_subnet_name(self, subnet_resource: str) -> str:
        return subnet_resource.rsplit(sep="/", maxsplit=1)[1]
