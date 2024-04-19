from typing import Optional

from datacrunch import DataCrunchClient
from datacrunch.exceptions import APIException
from datacrunch.instances.instances import Instance

from dstack._internal.core.errors import NoCapacityError
from dstack._internal.utils.ssh import get_public_key_fingerprint


class DataCrunchAPIClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client = DataCrunchClient(client_id, client_secret)

    def delete_instance(self, instance_id: str) -> None:
        try:
            self.client.instances.action(id_list=[instance_id], action="delete")
        except APIException:
            pass

    def get_or_create_ssh_key(self, name: str, public_key: str) -> str:
        fingerprint = get_public_key_fingerprint(public_key)
        keys = self.client.ssh_keys.get()
        found_keys = [
            key for key in keys if fingerprint == get_public_key_fingerprint(key.public_key)
        ]
        if found_keys:
            key = found_keys[0]
            return key.id

        key = self.client.ssh_keys.create(name, public_key)
        return key.id

    def get_or_create_startup_scrpit(self, name: str, script: str) -> str:
        scripts = self.client.startup_scripts.get()
        found_scripts = [startup_script for startup_script in scripts if script == startup_script]
        if found_scripts:
            startup_script = found_scripts[0]
            return startup_script.id

        startup_script = self.client.startup_scripts.create(name, script)
        return startup_script.id

    def get_instance_by_id(self, instance_id: str) -> Optional[Instance]:
        try:
            return self.client.instances.get_by_id(instance_id)
        except APIException:
            return None

    def deploy_instance(
        self,
        instance_type,
        image,
        ssh_key_ids,
        hostname,
        description,
        startup_script_id,
        disk_size,
        is_spot=True,
        location="FIN-01",
    ) -> Instance:
        try:
            instance = self.client.instances.create(
                instance_type=instance_type,
                image=image,
                ssh_key_ids=ssh_key_ids,
                hostname=hostname,
                description=description,
                startup_script_id=startup_script_id,
                is_spot=is_spot,
                location=location,
                os_volume={"name": "OS volume", "size": disk_size},
            )
        except APIException:
            raise NoCapacityError()

        return instance
