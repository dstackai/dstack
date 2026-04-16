from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.imports import Import, ImportExport, ImportExportedFleet
from dstack._internal.server.models import (
    ExportedFleetModel,
    ExportModel,
    FleetModel,
    ImportModel,
    ProjectModel,
)
from dstack._internal.server.services.exports import get_export_model_by_name_for_update
from dstack._internal.server.services.projects import get_project_model_by_name


async def list_imports(session: AsyncSession, project: ProjectModel) -> list[Import]:
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
            )
        )
        .order_by(ImportModel.created_at.desc())
    )
    imports = res.scalars().all()
    return [import_model_to_import(imp) for imp in imports]


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
        export.imports = [
            imp for imp in export.imports if imp.project.name.lower() != project.name.lower()
        ]
        await session.commit()


def import_model_to_import(import_model: ImportModel) -> Import:
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
        ),
    )
