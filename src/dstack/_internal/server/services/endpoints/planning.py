from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.runs import JobPlan, RunPlan, RunSpec
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.services import runs as runs_services
from dstack._internal.server.services import users as users_services
from dstack._internal.server.services.endpoints.names import get_endpoint_serving_run_name
from dstack._internal.server.services.endpoints.presets import (
    EndpointPreset,
    EndpointPresetService,
    get_endpoint_preset_service,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class EndpointPresetPlan:
    """A preset selected by endpoint planning and the run plan computed from it."""

    preset: EndpointPreset
    run_plan: RunPlan


@dataclass(frozen=True)
class EndpointPresetPlanningResult:
    """Preset planning result split into provisionable and no-offer matches."""

    provisionable: Optional[EndpointPresetPlan] = None
    unprovisionable: Optional[EndpointPresetPlan] = None


async def find_matching_preset_plan(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    endpoint_name: Optional[str],
    endpoint_configuration: EndpointConfiguration,
    max_offers: int = 1,
    preset_service: Optional[EndpointPresetService] = None,
) -> Optional[EndpointPresetPlan]:
    result = await find_preset_planning_result(
        session=session,
        project=project,
        user=user,
        endpoint_name=endpoint_name,
        endpoint_configuration=endpoint_configuration,
        max_offers=max_offers,
        preset_service=preset_service,
    )
    return result.provisionable


async def find_preset_planning_result(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    endpoint_name: Optional[str],
    endpoint_configuration: EndpointConfiguration,
    max_offers: int = 1,
    preset_service: Optional[EndpointPresetService] = None,
) -> EndpointPresetPlanningResult:
    if preset_service is None:
        preset_service = get_endpoint_preset_service()

    endpoint_model = endpoint_configuration.model.lower()
    presets = [
        preset
        for preset in await preset_service.list_presets()
        if preset.model.lower() == endpoint_model
    ]
    if not presets:
        return EndpointPresetPlanningResult()

    user = await _ensure_user_has_ssh_key(session=session, user=user)
    first_unprovisionable_preset: Optional[EndpointPresetPlan] = None
    for preset in presets:
        try:
            run_spec = build_preset_run_spec(
                endpoint_name=endpoint_name,
                endpoint_configuration=endpoint_configuration,
                preset=preset,
            )
            _validate_run_spec_env_resolved(run_spec)
            run_plan = await runs_services.get_plan(
                session=session,
                project=project,
                user=user,
                run_spec=run_spec,
                max_offers=max_offers,
            )
        except (ServerClientError, ValueError) as e:
            logger.warning("Skipping endpoint preset %s: %s", preset.name, e)
            continue
        preset_plan = EndpointPresetPlan(preset=preset, run_plan=run_plan)
        if _run_plan_has_available_offers(run_plan.job_plans):
            return EndpointPresetPlanningResult(
                provisionable=preset_plan,
                unprovisionable=first_unprovisionable_preset,
            )
        if first_unprovisionable_preset is None:
            first_unprovisionable_preset = preset_plan
    return EndpointPresetPlanningResult(unprovisionable=first_unprovisionable_preset)


def build_preset_service_configuration(
    endpoint_name: Optional[str],
    endpoint_configuration: EndpointConfiguration,
    preset: EndpointPreset,
) -> ServiceConfiguration:
    service_configuration = preset.configuration.copy(deep=True)
    service_configuration.name = get_endpoint_serving_run_name(endpoint_name)
    service_configuration.env.update(endpoint_configuration.env)
    for field in ProfileParams.__fields__:
        value = getattr(endpoint_configuration, field)
        if value is not None:
            setattr(service_configuration, field, value)
    return service_configuration


def build_preset_run_spec(
    endpoint_name: Optional[str],
    endpoint_configuration: EndpointConfiguration,
    preset: EndpointPreset,
) -> RunSpec:
    service_configuration = build_preset_service_configuration(
        endpoint_name=endpoint_name,
        endpoint_configuration=endpoint_configuration,
        preset=preset,
    )
    return RunSpec(
        run_name=service_configuration.name,
        configuration=service_configuration,
    )


def _validate_run_spec_env_resolved(run_spec: RunSpec) -> None:
    unresolved = [
        key for key, value in run_spec.configuration.env.items() if isinstance(value, EnvSentinel)
    ]
    if unresolved:
        raise ValueError("preset env is unresolved: " + ", ".join(sorted(unresolved)))


async def _ensure_user_has_ssh_key(
    session: AsyncSession,
    user: UserModel,
) -> UserModel:
    if user.ssh_public_key:
        return user
    refreshed_user = await users_services.refresh_ssh_key(session=session, actor=user)
    if refreshed_user is None:
        return user
    return refreshed_user


def _run_plan_has_available_offers(job_plans: Sequence[JobPlan]) -> bool:
    return bool(job_plans) and all(
        any(offer.availability.is_available() for offer in job_plan.offers)
        for job_plan in job_plans
    )
