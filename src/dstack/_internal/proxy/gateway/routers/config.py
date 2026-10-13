import os
import signal
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends

from dstack._internal.proxy.gateway import otel
from dstack._internal.proxy.gateway.deps import get_gateway_proxy_repo
from dstack._internal.proxy.gateway.models import ACMESettings, GlobalProxyConfig
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.schemas.common import OkResponse
from dstack._internal.proxy.gateway.schemas.config import ConfigRequest

router = APIRouter()


@router.post("")
async def update_global_config(
    body: ConfigRequest,
    repo: Annotated[GatewayProxyRepo, Depends(get_gateway_proxy_repo)],
    background_tasks: BackgroundTasks,
) -> OkResponse:
    await repo.set_config(
        GlobalProxyConfig(
            acme_settings=ACMESettings(
                server=body.acme_server,
                eab_kid=body.acme_eab_kid,
                eab_hmac_key=body.acme_eab_hmac_key,
            ),
            otel_settings=body.otel_settings,
        ),
    )
    if otel.apply_settings(body.otel_settings):
        # The new settings are saved and will be applied on startup. Uvicorn shuts down
        # gracefully on SIGTERM, then systemd starts the app again (`Restart=always`).
        background_tasks.add_task(os.kill, os.getpid(), signal.SIGTERM)
    return OkResponse()
