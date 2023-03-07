import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml
from google.cloud import compute_v1, exceptions, storage
from google.oauth2 import service_account
from rich.prompt import Confirm, Prompt
from simple_term_menu import TerminalMenu

from dstack.cli.common import ask_choice, console
from dstack.core.config import BackendConfig, Configurator, get_config_path
from dstack.core.error import ConfigError

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
    def deserialize(cls, data: Dict) -> Optional["GCPConfig"]:
        if data.get("backend") != "gcp":
            raise ConfigError(f"Not a GCP config")

        try:
            project_id = data["project"]
            region = data["region"]
            zone = data["zone"]
            bucket_name = data["bucket"]
            vpc = data["vpc"]
            subnet = data["subnet"]
        except KeyError:
            raise ConfigError("Cannot load config")

        credentials_file = data.get("credentials_file")
        return cls(
            project_id=project_id,
            region=region,
            zone=zone,
            bucket_name=bucket_name,
            vpc=vpc,
            subnet=subnet,
            credentials_file=credentials_file,
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

    def get_config(self, data: Dict) -> BackendConfig:
        return GCPConfig.deserialize(data=data)

    def parse_args(self, args: list = []):
        pass

    def configure_hub(self, data: Dict):
        pass

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
        console.print(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Choose storage bucket[/bold] "
            "[gray46]Use arrows to move, type to filter[/gray46]"
        )
        if default_bucket is None:
            default_bucket = f"dstack-{self.project_id}-{self.region}"
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
        vpc_subnet_values = sorted(
            [(s["vpc"], s["subnet"]) for s in subnets], key=lambda t: t != no_preference_vpc_subnet
        )
        vpc_subnet_labels = [
            f"{t[1]} [{t[0]}]" if t != no_preference_vpc_subnet else "Default [no preference]"
            for t in vpc_subnet_values
        ]
        vpc, subnet = ask_choice(
            "Choose VPC subnet",
            vpc_subnet_labels,
            vpc_subnet_values,
            (default_vpc, default_subnet),
        )
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
