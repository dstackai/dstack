from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.gcp import AnyGCPCreds, GCPStoredConfig


class GCPConfig(GCPStoredConfig, BackendConfig):
    creds: AnyGCPCreds

    @property
    def allocate_public_ips(self) -> bool:
        if self.public_ips is not None:
            return self.public_ips
        return True

    @property
    def vpc_resource_name(self) -> str:
        vpc_name = self.vpc_name
        if vpc_name is None:
            vpc_name = "default"
        project_id = self.project_id
        if self.vpc_project_id is not None:
            project_id = self.vpc_project_id
        return f"projects/{project_id}/global/networks/{vpc_name}"
