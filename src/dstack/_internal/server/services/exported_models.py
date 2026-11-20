"""
Application logic related to models that projects export to other projects.
"""

import uuid
from collections.abc import Iterable
from typing import Optional

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only, raiseload

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.common import EntityReference, validate_json_extra_ignore
from dstack._internal.core.models.runs import RunStatus, ServiceSpec
from dstack._internal.core.models.services import AnyModel
from dstack._internal.server.models import (
    BackendModel,
    ExportedModelModel,
    ExportModel,
    GatewayModel,
    ProjectModel,
    RunModel,
)
from dstack._internal.utils.common import is_gateway_domain_fixed


async def check_can_export_models(
    session: AsyncSession, export: ExportModel, names: list[str]
) -> None:
    """
    Checks that the running services of the export's project that declare the models
    can serve them to importer projects.

    A model that no running service declares can be added to the export:
    importer projects access it once a service that can serve it to them starts.
    """
    services = await _list_services_with_models(session, RunModel.project_id == export.project.id)
    for name in names:
        services_with_model = [
            (run_model, model) for run_model, model in services if model.name == name
        ]
        if not services_with_model:
            continue
        if any(
            can_serve_importer_projects(model, run_model.gateway)
            for run_model, model in services_with_model
        ):
            continue
        missing = "; ".join(
            _get_cannot_serve_message(run_model, model) for run_model, model in services_with_model
        )
        raise ServerClientError(f"Cannot add {name!r} to {export.name!r}: {missing}")


async def check_can_update_service(
    session: AsyncSession, run_model: RunModel, previous_gateway: Optional[GatewayModel]
) -> None:
    """
    Checks that the in-place update of the service does not leave a model exported
    by its project with no service that can serve the model to importer projects.

    The update is refused only if the service could serve the model before the update,
    can't serve it after the update, and no other running service of the project can.

    Call it once the update is applied to `run_model`, with `run_model.gateway` loaded.
    `previous_gateway` is the gateway the service ran on before the update.
    """
    # The model of a service is not updated in place, so only its gateway changes.
    model = get_service_model(run_model)
    if model is None:
        return
    if not can_serve_importer_projects(model, previous_gateway):
        return
    if can_serve_importer_projects(model, run_model.gateway):
        return
    export_names = await _list_export_names(session, [(run_model.project_id, model.name)])
    model_export_names = export_names.get((run_model.project_id, model.name))
    if not model_export_names:
        return
    other_services = await _list_services_with_models(
        session, RunModel.project_id == run_model.project_id, RunModel.id != run_model.id
    )
    if any(
        other_model.name == model.name
        and can_serve_importer_projects(other_model, other_run_model.gateway)
        for other_run_model, other_model in other_services
    ):
        return
    raise ServerClientError(
        f"Cannot update {run_model.run_name!r}: {model.name!r} is exported by"
        f" {', '.join(map(repr, model_export_names))},"
        " and no other service would serve it to importer projects."
        " Start another service for the model, or remove it from the export first."
    )


async def check_can_set_gateway_domain(
    session: AsyncSession, gateway_model: GatewayModel, domain: Optional[str]
) -> None:
    """
    Checks that the new domain of the gateway does not stop a service on the gateway
    from serving an exported model to importer projects. A service serves them only
    on a gateway with a fixed domain, so the domain can be neither removed
    nor given `${{ run.project_name }}`.

    Call it before the domain of `gateway_model` is updated.
    """
    if domain is not None and is_gateway_domain_fixed(domain):
        return
    services = await _list_services_with_models(session, RunModel.gateway_id == gateway_model.id)
    serving_services = [
        (run_model, model)
        for run_model, model in services
        if can_serve_importer_projects(model, run_model.gateway)
    ]
    export_names = await _list_export_names(
        session, [(run_model.project_id, model.name) for run_model, model in serving_services]
    )
    for run_model, model in serving_services:
        model_export_names = export_names.get((run_model.project_id, model.name))
        if not model_export_names:
            continue
        raise ServerClientError(
            f"Cannot remove the domain of {gateway_model.name!r}"
            f" or put ${{{{ run.project_name }}}} into it: {model.name!r} is exported by"
            f" {', '.join(map(repr, model_export_names))}, and {run_model.run_name!r}"
            " serves it to importer projects from this gateway."
            " Move the service to another gateway, or remove the model from the export first."
        )


async def get_services_serving_importer_projects(
    session: AsyncSession, project_ids: Iterable[uuid.UUID]
) -> dict[tuple[uuid.UUID, str], RunModel]:
    """
    Returns the running services of the projects that can serve their models
    to importer projects, by project ID and model name, with the gateways they run on.

    If several services of a project declare the same model, returns the last submitted one.
    """
    project_ids = list(project_ids)
    if not project_ids:
        return {}
    services = await _list_services_with_models(session, RunModel.project_id.in_(project_ids))
    return {
        (run_model.project_id, model.name): run_model
        for run_model, model in services
        if can_serve_importer_projects(model, run_model.gateway)
    }


def can_serve_importer_projects(model: AnyModel, gateway_model: Optional[GatewayModel]) -> bool:
    """
    Returns `True` if a service that declares `model` and runs on `gateway_model`
    can serve the model to the projects that import it.

    Only requests to models with the `openai` format are metered, and only a gateway
    with a fixed domain gives every importer project its model endpoint on one host.
    """
    return (
        model.format == "openai"
        and gateway_model is not None
        and gateway_model.wildcard_domain is not None
        and is_gateway_domain_fixed(gateway_model.wildcard_domain)
    )


def get_service_model(run_model: RunModel) -> Optional[AnyModel]:
    """
    Returns the model that the service declares, as it is registered on the gateway.
    `None` if the run is not a service or the service declares no model.
    """
    if run_model.service_spec is None:
        return None
    service_spec = validate_json_extra_ignore(ServiceSpec, run_model.service_spec)
    return service_spec.get_model_options()


def get_running_service_filters() -> list[ColumnElement[bool]]:
    """
    Returns the filters of the runs whose services are running:
    not deleted, not finished, not terminating.
    `GatewayReplicaPipeline` registers these services on gateway replicas.
    """
    return [
        RunModel.deleted == False,
        RunModel.status.not_in(RunStatus.finished_statuses() + [RunStatus.TERMINATING]),
    ]


def _get_cannot_serve_message(run_model: RunModel, model: AnyModel) -> str:
    if model.format != "openai":
        return f"{run_model.run_name!r} declares it with format {model.format}, not openai"
    gateway_model = run_model.gateway
    if gateway_model is None:
        return f"{run_model.run_name!r} runs without a gateway"
    gateway_ref = EntityReference(
        project=(
            gateway_model.project.name
            if gateway_model.project_id != run_model.project_id
            else None
        ),
        name=gateway_model.name,
    )
    if gateway_model.wildcard_domain is None:
        return f"{run_model.run_name!r} runs on {gateway_ref.format()!r}, which has no domain"
    return (
        f"{run_model.run_name!r} runs on {gateway_ref.format()!r},"
        " which has ${{ run.project_name }} in its domain"
    )


async def _list_services_with_models(
    session: AsyncSession, *run_filters: ColumnElement[bool]
) -> list[tuple[RunModel, AnyModel]]:
    """
    Lists the running services that declare a model, with the gateways they run on,
    in the order they were submitted.
    """
    res = await session.execute(
        select(RunModel)
        .where(*run_filters, *get_running_service_filters())
        .options(
            load_only(RunModel.project_id, RunModel.run_name, RunModel.service_spec),
            joinedload(RunModel.gateway).options(
                joinedload(GatewayModel.backend).load_only(BackendModel.type),
                joinedload(GatewayModel.project).load_only(ProjectModel.name),
            ),
            raiseload(RunModel.jobs),
        )
        .order_by(RunModel.submitted_at)
    )
    services = []
    for run_model in res.scalars().all():
        model = get_service_model(run_model)
        if model is not None:
            services.append((run_model, model))
    return services


async def _list_export_names(
    session: AsyncSession, models: Iterable[tuple[uuid.UUID, str]]
) -> dict[tuple[uuid.UUID, str], list[str]]:
    """
    Returns the names of the exports that hold the models, oldest export first.
    The models are given and returned by the ID of the export's project and the model's name.
    """
    models = set(models)
    if not models:
        return {}
    res = await session.execute(
        select(ExportModel.project_id, ExportedModelModel.name, ExportModel.name)
        .join(ExportedModelModel, ExportedModelModel.export_id == ExportModel.id)
        .where(
            ExportModel.project_id.in_({project_id for project_id, _ in models}),
            ExportedModelModel.name.in_({model_name for _, model_name in models}),
        )
        .order_by(ExportModel.created_at)
    )
    export_names: dict[tuple[uuid.UUID, str], list[str]] = {}
    for project_id, model_name, export_name in res.all():
        if (project_id, model_name) in models:
            export_names.setdefault((project_id, model_name), []).append(export_name)
    return export_names
