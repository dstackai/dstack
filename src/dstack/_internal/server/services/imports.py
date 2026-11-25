import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from dstack._internal.core.errors import ResourceNotExistsError, ServerClientError
from dstack._internal.core.models.common import validate_json_extra_ignore
from dstack._internal.core.models.imports import (
    Import,
    ImportExport,
    ImportExportedFleet,
    ImportExportedGateway,
    ImportExportedModel,
    ListImportsResponse,
)
from dstack._internal.core.models.runs import ServiceSpec
from dstack._internal.server.models import (
    ExportedFleetModel,
    ExportedGatewayModel,
    ExportModel,
    FleetModel,
    GatewayModel,
    ImportModel,
    ProjectModel,
    RunModel,
)
from dstack._internal.server.services.exported_models import (
    get_services_serving_importer_projects,
)
from dstack._internal.server.services.exports import (
    EXPORTS_NOT_SUPPORTED_MESSAGE,
    EXPORTS_PHASE_OUT_MESSAGE,
    are_exports_enabled,
    get_export_model_by_name_for_update,
)
from dstack._internal.server.services.gateways import get_gateway_configuration
from dstack._internal.server.services.projects import get_project_model_by_name
from dstack._internal.server.services.services import get_gateway_endpoint_url
from dstack._internal.utils.common import get_or_error


async def list_imports(session: AsyncSession, project: ProjectModel) -> ListImportsResponse:
    res = await session.execute(
        select(ImportModel)
        .where(ImportModel.project_id == project.id)
        .options(
            joinedload(ImportModel.export)
            .load_only(ExportModel.id, ExportModel.name)
            .options(
                joinedload(ExportModel.project).load_only(ProjectModel.name),
                selectinload(
                    ExportModel.exported_fleets.and_(
                        ExportedFleetModel.fleet.has(FleetModel.deleted == False)
                    )
                )
                .joinedload(ExportedFleetModel.fleet)
                .load_only(FleetModel.id, FleetModel.name),
                selectinload(ExportModel.exported_gateways)
                .joinedload(ExportedGatewayModel.gateway)
                .load_only(GatewayModel.id, GatewayModel.name),
                selectinload(ExportModel.exported_models),
            )
        )
        .order_by(ImportModel.created_at.desc())
    )
    import_models = res.scalars().all()
    services = await get_services_serving_importer_projects(
        session,
        project_ids={imp.export.project.id for imp in import_models if imp.export.exported_models},
    )
    imports = [
        import_model_to_import(imp, _get_import_exported_models(imp.export, project, services))
        for imp in import_models
    ]
    warnings = []
    if not are_exports_enabled():
        if not imports:
            raise ServerClientError(EXPORTS_NOT_SUPPORTED_MESSAGE)
        else:
            warnings.append(EXPORTS_PHASE_OUT_MESSAGE)
    return ListImportsResponse(
        imports=imports,
        warnings=warnings,
    )


async def delete_import(
    session: AsyncSession,
    project: ProjectModel,
    export_name: str,
    export_project_name: str,
) -> None:
    # Always the same error, so as not to expose the existence of exports
    # that are not imported in this project.
    not_found_error = ResourceNotExistsError(
        f"Import '{export_project_name}/{export_name}' not found in project {project.name!r}"
    )
    exporter_project = await get_project_model_by_name(session, export_project_name)
    if exporter_project is None:
        raise not_found_error
    async with get_export_model_by_name_for_update(
        session, exporter_project, export_name
    ) as export:
        if export is None:
            raise not_found_error
        if project.name.lower() not in {imp.project.name.lower() for imp in export.imports}:
            raise not_found_error
        if export.is_global:
            raise ServerClientError(
                f"'{export_project_name}/{export_name}' is a global export, cannot stop importing"
            )
        export.imports = [
            imp for imp in export.imports if imp.project.name.lower() != project.name.lower()
        ]
        await session.commit()


def import_model_to_import(
    import_model: ImportModel, exported_models: list[ImportExportedModel]
) -> Import:
    return Import(
        id=import_model.id,
        export=ImportExport(
            id=import_model.export.id,
            name=import_model.export.name,
            project_name=import_model.export.project.name,
            exported_fleets=[
                ImportExportedFleet(
                    id=ef.fleet.id,
                    name=ef.fleet.name,
                )
                for ef in import_model.export.exported_fleets
            ],
            exported_gateways=[
                ImportExportedGateway(
                    id=eg.gateway.id,
                    name=eg.gateway.name,
                )
                for eg in import_model.export.exported_gateways
            ],
            exported_models=exported_models,
        ),
    )


def _get_import_exported_models(
    export: ExportModel, project: ProjectModel, services: dict[tuple[uuid.UUID, str], RunModel]
) -> list[ImportExportedModel]:
    """
    Returns the models of the export with their URLs for the importer `project`.
    The URLs are built from `services`, the services that serve the models now,
    so they follow the services.
    """
    exported_models = []
    for exported_model in export.exported_models:
        base_url = None
        run_model = services.get((export.project.id, exported_model.name))
        if run_model is not None:
            service_spec = validate_json_extra_ignore(
                ServiceSpec, get_or_error(run_model.service_spec)
            )
            base_url = get_gateway_endpoint_url(
                service_url=service_spec.url,
                configuration=get_gateway_configuration(get_or_error(run_model.gateway)),
                project_name=project.name,
            )
        exported_models.append(ImportExportedModel(name=exported_model.name, base_url=base_url))
    return exported_models
