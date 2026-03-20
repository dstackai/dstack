from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from dstack._internal.core.models.imports import Import, ImportExport, ImportExportedFleet
from dstack._internal.server.models import (
    ExportedFleetModel,
    ExportModel,
    FleetModel,
    ImportModel,
    ProjectModel,
)


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
