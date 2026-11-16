from typing import Annotated

from fastapi import APIRouter, Depends

from dstack._internal.proxy.gateway.deps import (
    GatewayDependencyInjector,
    get_gateway_injector,
    get_gateway_proxy_repo,
    get_metering,
)
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.schemas.common import OkResponse
from dstack._internal.proxy.gateway.schemas.config import ConfigRequest
from dstack._internal.proxy.gateway.services.metering import MeteringCollector
from dstack._internal.proxy.lib.errors import ProxyError
from dstack._internal.proxy.lib.models import OpenAIChatModelFormat

router = APIRouter()


@router.post("")
async def update_global_config(
    body: ConfigRequest,
    repo: Annotated[GatewayProxyRepo, Depends(get_gateway_proxy_repo)],
    metering: Annotated[MeteringCollector, Depends(get_metering)],
    injector: Annotated[GatewayDependencyInjector, Depends(get_gateway_injector)],
) -> OkResponse:
    async with injector.config_lock:
        config = await repo.get_config()
        acme_changes = {
            name.removeprefix("acme_"): getattr(body, name)
            for name in body.model_fields_set
            if name.startswith("acme_")
        }
        profiles = config.usage_metering_profiles
        if "usage_metering_profiles" in body.model_fields_set:
            if body.usage_metering_profiles is None:
                raise ProxyError("Metering profiles must be an object; omit to preserve")
            profiles = body.usage_metering_profiles
            eligible = set()
            for service in await repo.list_services():
                for model in await repo.list_models(service.project_name):
                    if model.run_name == service.run_name and isinstance(
                        model.format_spec, OpenAIChatModelFormat
                    ):
                        eligible.add(service.id)
            if not profiles.keys() <= eligible:
                raise ProxyError("Metering requires a registered OpenAI service with a stable ID")
        updated = config.model_copy(
            update={
                "acme_settings": config.acme_settings.model_copy(update=acme_changes),
                "usage_metering_profiles": profiles,
            }
        )

        async def persist() -> None:
            await repo.set_config(updated)

        await metering.configure_profiles(profiles, persist=persist)
        return OkResponse()
