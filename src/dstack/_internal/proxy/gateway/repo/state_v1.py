"""
Migration from the legacy state.json file of dstack-gateway to the new
state-v2.json file of dstack-proxy.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.proxy.gateway.models import ACMESettings, GlobalProxyConfig, ModelEntrypoint
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo, State
from dstack._internal.proxy.lib.models import (
    AnyModelFormat,
    ChatModel,
    OpenAIChatModelFormat,
    Project,
    Replica,
    Service,
    TGIChatModelFormat,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def migrate_from_state_v1(v1_file: Path, v2_file: Path, keys_dir: Path) -> None:
    if v2_file.exists() or not v1_file.exists():
        return
    state_v1 = json.loads(v1_file.read_text())
    state = parse_state_v1(state_v1, keys_dir)
    repo = GatewayProxyRepo(state=state, file=v2_file)
    repo.save()
    logger.info("Successfully migrated state from %s to %s", v1_file, v2_file)


def parse_state_v1(state_v1: dict, keys_dir: Path) -> State:
    services, models = get_services_models(state_v1)
    return State(
        services=services,
        models=models,
        entrypoints=get_entrypoints(state_v1.get("store", {})),
        projects=get_projects(state_v1.get("store", {}).get("projects", {}), keys_dir),
        config=get_config(state_v1.get("store", {}).get("nginx", {}).get("acme_settings", {})),
    )


def get_services_models(
    state_v1: dict,
) -> tuple[dict[str, dict[str, Service]], dict[str, dict[str, ChatModel]]]:
    service_id_to_project_name = {}
    for project_name, project_services in state_v1.get("store", {}).get("projects", {}).items():
        for service_id in project_services:
            service_id_to_project_name[service_id] = project_name

    services: dict[str, dict[str, Service]] = {}
    models: dict[str, dict[str, ChatModel]] = {}
    for service in state_v1.get("store", {}).get("services", {}).values():
        project_name = service_id_to_project_name[service["id"]]
        replicas = []
        for replica in service.get("replicas", []):
            replicas.append(parse_replica(replica))
        parsed_service = Service(
            project_name=project_name,
            run_name=service["domain"].split(".")[0],
            domain=service["domain"],
            https=service.get("https", True),
            auth=service["auth"],
            client_max_body_size=service.get("client_max_body_size", 1024 * 1024),
            replicas=tuple(replicas),
        )
        services.setdefault(project_name, {})[parsed_service.run_name] = parsed_service
        if model := service.get("options", {}).get("openai", {}).get("model", {}):
            parsed_model = parse_model(
                project_name, parsed_service.run_name, model, state_v1["openai"]["index"]
            )
            if parsed_model is not None:
                models.setdefault(project_name, {})[parsed_model.name] = parsed_model

    return services, models


def parse_replica(replica: dict) -> Replica:
    ssh_proxy = None
    if (ssh_proxy_destination := replica.get("ssh_jump_host")) and (
        ssh_proxy_port := replica.get("ssh_jump_port")
    ):
        proxy_user, proxy_host = ssh_proxy_destination.split("@")
        ssh_proxy = SSHConnectionParams(
            hostname=proxy_host,
            username=proxy_user,
            port=ssh_proxy_port,
        )
    return Replica(
        id=replica["id"],
        app_port=replica["app_port"],
        ssh_destination=replica["ssh_host"],
        ssh_port=replica["ssh_port"],
        ssh_proxy=ssh_proxy,
    )


def parse_model(
    project_name: str, run_name: str, model: dict, openai_index: dict
) -> Optional[ChatModel]:
    created_ts = (
        openai_index.get(project_name, {}).get("chat", {}).get(model["name"], {}).get("created")
    )
    if created_ts is None:
        # some models can be missing in the index, most likely due to a bug
        return None
    format_spec: AnyModelFormat
    if model["format"] == "tgi":
        format_spec = TGIChatModelFormat(
            chat_template=model["chat_template"], eos_token=model["eos_token"]
        )
    else:
        format_spec = OpenAIChatModelFormat(prefix=model["prefix"])
    return ChatModel(
        project_name=project_name,
        name=model["name"],
        created_at=datetime.fromtimestamp(created_ts),
        run_name=run_name,
        format_spec=format_spec,
    )


def get_entrypoints(store: dict) -> dict[str, ModelEntrypoint]:
    entrypoint_domain_to_project_name = {}
    for entrypoint_domain, (project_name, _) in store.get("entrypoints", {}).items():
        entrypoint_domain_to_project_name[entrypoint_domain] = project_name

    entrypoints = {}
    for site_config in store.get("nginx", {}).get("configs", {}).values():
        if site_config["type"] == "entrypoint":
            entrypoint = ModelEntrypoint(
                project_name=entrypoint_domain_to_project_name[site_config["domain"]],
                domain=site_config["domain"],
                https=site_config["https"],
            )
            entrypoints[entrypoint.project_name] = entrypoint

    return entrypoints


def get_projects(project_names: Iterable[str], keys_dir: Path) -> dict[str, Project]:
    projects = {}
    for project_name in project_names:
        projects[project_name] = Project(
            name=project_name,
            ssh_private_key=(keys_dir / project_name).read_text(),
        )
    return projects


def get_config(acme_settings: dict) -> GlobalProxyConfig:
    return GlobalProxyConfig(
        acme_settings=ACMESettings(
            server=acme_settings.get("server"),
            eab_kid=acme_settings.get("eab_kid"),
            eab_hmac_key=acme_settings.get("eab_hmac_key"),
        )
    )
