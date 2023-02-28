import os
from pathlib import Path
from typing import Dict, Optional

import yaml
from google.cloud import compute_v1, exceptions, storage
from google.oauth2 import service_account
from rich.prompt import Confirm, Prompt
from simple_term_menu import TerminalMenu

from dstack.cli.common import ask_choice, console
from dstack.core.config import BackendConfig, get_config_path


class GCPConfig:
    def __init__(
        self,
        project_id: str,
        zone: str,
        bucket_name: str,
        credentials: Optional[Dict] = None,
    ):
        self.project_id = project_id
        self.zone = zone
        self.bucket_name = bucket_name
        self.credentials = credentials

    def serialize(self) -> Dict:
        return {
            "backend": "gcp",
            "project": self.project_id,
            "zone": self.zone,
            "bucket": self.bucket_name,
        }

    def serialize_yaml(self) -> str:
        return yaml.dump(self.serialize())

    @classmethod
    def deserialize(cls, data: Dict) -> "GCPConfig":
        return cls(project_id=data["project"], zone=data["zone"], bucket_name=data["bucket"])

    @classmethod
    def deserialize_yaml(cls, yaml_content: str) -> "GCPConfig":
        return cls.deserialize(yaml.load(yaml_content, yaml.FullLoader))


class GCPConfigurator(BackendConfig):
    @property
    def name(self):
        return "gcp"

    @classmethod
    def load(cls, path: Path = get_config_path()) -> GCPConfig:
        with open(path) as f:
            return GCPConfig.deserialize_yaml(f.read())

    def save(self, config: GCPConfig, path: Path = get_config_path()):
        with open(path, "w+") as f:
            f.write(config.serialize_yaml())

    def configure(self):
        credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_file is None:
            console.print(
                "[red bold]✗[/red bold] GOOGLE_APPLICATION_CREDENTIALS is not set."
                " It should point to the service account credentials file."
                " Learn more about service account credentials: https://cloud.google.com/iam/docs/creating-managing-service-account-keys"
            )
            exit(1)

        zone = None
        bucket_name = None
        try:
            config = self.load()
        except Exception:
            pass
        else:
            zone = config.zone
            bucket_name = config.bucket_name

        self.credentials = self._get_credentials(credentials_file)
        self.project_id = self.credentials.project_id

        self.zone = self._ask_zone(zone)
        self.bucket_name = self._ask_bucket(default_bucket=bucket_name)

        config = GCPConfig(
            project_id=self.project_id,
            zone=self.zone,
            bucket_name=bucket_name,
        )
        self.save(config)
        console.print(f"[grey58]OK[/]")

    def _get_credentials(self, credentials_file: str) -> service_account.Credentials:
        try:
            credentials = service_account.Credentials.from_service_account_file(credentials_file)
            storage_client = storage.Client(credentials=credentials)
            storage_client.list_buckets(max_results=1)
        except Exception as e:
            console.print(
                f"[red bold]✗[/red bold] Error while checking GCP credentials:\n{e}",
            )
            exit(1)
        return credentials

    def _ask_zone(self, default_zone: Optional[str]) -> str:
        regions_client = compute_v1.RegionsClient(credentials=self.credentials)
        zones_client = compute_v1.ZonesClient(credentials=self.credentials)
        default_region = None
        if default_zone is not None:
            get_zone_request = compute_v1.GetZoneRequest(
                project=self.project_id, zone=default_zone
            )
            zone = zones_client.get(get_zone_request)
            default_region = self._get_resource_name(zone.region)
        list_regions_request = compute_v1.ListRegionsRequest(project=self.project_id)
        regions = regions_client.list(list_regions_request)
        region_names = [r.name for r in regions]
        if default_region is None:
            default_region = region_names[0]
        region_name = ask_choice(
            "Choose GCP region",
            region_names,
            region_names,
            default_region,
        )
        region = {r.name: r for r in regions}[region_name]
        zone_names = [self._get_resource_name(z) for z in region.zones]
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
            default_bucket = f"dstack-{self.project_id}"
        bucket_options = [f"Default [{default_bucket}]", "Custom..."]
        bucket_menu = TerminalMenu(
            bucket_options,
            menu_cursor_style=["fg_red", "bold"],
            menu_highlight_style=["fg_red", "bold"],
            search_highlight_style=["fg_purple"],
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
            storage_client.get_bucket(bucket_name)
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
                # We create multi-region buckets by default
                location = self._get_zone_location(self.zone)
                storage_client.create_bucket(bucket_name, location=location)
                return True
            else:
                return False
        return True

    def _get_resource_name(self, resource_path: str) -> str:
        return resource_path.rsplit(sep="/", maxsplit=1)[1]

    def _get_zone_location(self, zone: str) -> str:
        if zone.startswith("asia"):
            return "ASIA"
        if zone.startswith("eu"):
            return "EU"
        return "US"
