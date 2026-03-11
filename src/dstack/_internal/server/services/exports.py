from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dstack._internal.core.errors import (
    ResourceExistsError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.exports import Export, ExportedFleet, ExportImport
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.server.db import get_db, is_db_postgres, is_db_sqlite
from dstack._internal.server.models import (
    ExportedFleetModel,
    ExportModel,
    FleetModel,
    ImportModel,
    ProjectModel,
    ProjectRole,
    UserModel,
)
from dstack._internal.server.services.fleets import get_fleet_spec, list_project_fleet_models
from dstack._internal.server.services.locking import get_locker, string_to_lock_id
from dstack._internal.server.services.projects import (
    get_user_project_role,
    list_user_project_models,
)


@asynccontextmanager
async def get_export_model_by_name_for_update(
    session: AsyncSession, project: ProjectModel, name: str
) -> AsyncGenerator[Optional[ExportModel], None]:
    """
    Fetch export from the database and lock it for update.

    **NOTE**: commit changes to the database before exiting from this context manager,
              so that in-memory locks are only released after commit.
    """
    filters = [
        ExportModel.project_id == project.id,
        ExportModel.name == name,
    ]
    res = await session.execute(select(ExportModel.id).where(*filters))
    export_id = res.scalars().one_or_none()
    if not export_id:
        yield None
    else:
        async with get_locker(get_db().dialect_name).lock_ctx(
            ExportModel.__tablename__, [export_id]
        ):
            # Refetch after lock
            res = await session.execute(
                select(ExportModel)
                .where(ExportModel.id == export_id, *filters)
                .options(
                    selectinload(
                        ExportModel.imports.and_(
                            ImportModel.project.has(ProjectModel.deleted == False)
                        )
                    )
                    .joinedload(ImportModel.project)
                    .load_only(ProjectModel.name),
                    selectinload(
                        ExportModel.exported_fleets.and_(
                            ExportedFleetModel.fleet.has(FleetModel.deleted == False)
                        )
                    )
                    .joinedload(ExportedFleetModel.fleet)
                    .load_only(FleetModel.name),
                )
                .with_for_update(key_share=True)
            )
            yield res.scalars().one_or_none()


async def export_exists(session: AsyncSession, project: ProjectModel, name: str) -> bool:
    res = await session.execute(
        select(func.count())
        .select_from(ExportModel)
        .where(ExportModel.project_id == project.id, ExportModel.name == name)
    )
    return res.scalar_one() > 0


async def create_export(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    name: str,
    importer_project_names: list[str],
    exported_fleet_names: list[str],
) -> Export:
    validate_dstack_resource_name(name)

    lock_namespace = f"export_names_{project.name}"
    if is_db_sqlite():
        # Start new transaction to see committed changes after lock
        await session.commit()
    elif is_db_postgres():
        await session.execute(
            select(func.pg_advisory_xact_lock(string_to_lock_id(lock_namespace)))
        )
    lock, _ = get_locker(get_db().dialect_name).get_lockset(lock_namespace)

    async with lock:
        if await export_exists(session, project, name):
            raise ResourceExistsError(
                f"Export {name!r} already exists in project {project.name!r}"
            )
        export = ExportModel(
            name=name,
            project=project,
            imports=[],
            exported_fleets=[],
        )
        await add_importer_projects(session, user, export, importer_project_names)
        await add_exported_fleets(session, export, exported_fleet_names)
        session.add(export)
        await session.commit()
    return export_model_to_export(export)


async def update_export(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    name: str,
    add_importer_project_names: list[str],
    remove_importer_project_names: list[str],
    add_exported_fleet_names: list[str],
    remove_exported_fleet_names: list[str],
) -> Export:
    async with get_export_model_by_name_for_update(session, project, name) as export:
        if export is None:
            raise ResourceNotExistsError(f"Export {name!r} not found in project {project.name!r}")

        if (
            not add_importer_project_names
            and not remove_importer_project_names
            and not add_exported_fleet_names
            and not remove_exported_fleet_names
        ):
            raise ServerClientError("No changes specified")

        add_importer_project_names = list(map(str.lower, add_importer_project_names))
        remove_importer_project_names = list(map(str.lower, remove_importer_project_names))

        add_remove_conflict_projects = set(add_importer_project_names) & set(
            remove_importer_project_names
        )
        if add_remove_conflict_projects:
            raise ServerClientError(
                f"Projects {add_remove_conflict_projects} are listed for both addition and removal."
                " Cannot add and remove at the same time"
            )
        add_remove_conflict_fleets = set(add_exported_fleet_names) & set(
            remove_exported_fleet_names
        )
        if add_remove_conflict_fleets:
            raise ServerClientError(
                f"Fleets {add_remove_conflict_fleets} are listed for both addition and removal."
                " Cannot add and remove at the same time"
            )

        await add_importer_projects(session, user, export, add_importer_project_names)
        await add_exported_fleets(session, export, add_exported_fleet_names)
        await remove_importer_projects(export, remove_importer_project_names)
        await remove_exported_fleets(export, remove_exported_fleet_names)

        await session.commit()
    return export_model_to_export(export)


async def add_importer_projects(
    session: AsyncSession, user: UserModel, export: ExportModel, names: list[str]
) -> None:
    if not names:
        return
    names = list(map(str.lower, names))
    if len(names) != len(set(names)):
        raise ServerClientError("Some importer projects are listed for addition more than once")
    already_importing = {imp.project.name.lower() for imp in export.imports} & set(names)
    if already_importing:
        raise ServerClientError(
            f"Projects {already_importing} are already importing export {export.name!r}"
        )
    if export.project.name.lower() in names:
        raise ServerClientError(f"Project {export.project.name!r} cannot import from itself")
    projects = await list_user_project_models(session, user, only_names=True, include_members=True)
    projects = [p for p in projects if p.name.lower() in names]
    if user.global_role != GlobalRole.ADMIN:
        projects = [p for p in projects if get_user_project_role(user, p) == ProjectRole.ADMIN]
    if missing := set(names) - {p.name.lower() for p in projects}:
        raise ServerClientError(
            f"Projects {missing} not found or you are not allowed to add them as importers."
            " Only project admins can add a project as importer"
        )
    for project in projects:
        export.imports.append(ImportModel(project=project))


async def add_exported_fleets(
    session: AsyncSession, export: ExportModel, names: list[str]
) -> None:
    if not names:
        return
    if len(names) != len(set(names)):
        raise ServerClientError("Some fleets are listed for addition more than once")
    already_exported = {ef.fleet.name for ef in export.exported_fleets} & set(names)
    if already_exported:
        raise ServerClientError(
            f"Fleets {already_exported} are already exported by export {export.name!r}"
        )
    fleets = await list_project_fleet_models(
        session=session,
        project=export.project,
        names=names,
        include_imported=False,
        include_deleted=False,
        include_instances=False,
    )
    if missing := set(names) - {f.name for f in fleets}:
        raise ResourceNotExistsError(
            f"Fleets {missing} not found in project {export.project.name!r}"
        )
    cloud_fleet_names = [
        f.name for f in fleets if get_fleet_spec(f).configuration.ssh_config is None
    ]
    if cloud_fleet_names:
        raise ServerClientError(
            f"Fleets {cloud_fleet_names} are cloud fleets. Can only export SSH fleets"
        )
    for fleet in fleets:
        export.exported_fleets.append(ExportedFleetModel(fleet=fleet))


async def remove_importer_projects(export: ExportModel, names: list[str]) -> None:
    names = list(map(str.lower, names))
    if len(names) != len(set(names)):
        raise ServerClientError("Some importer projects are listed for removal more than once")
    existing = {imp.project.name.lower() for imp in export.imports}
    if missing := set(names) - existing:
        raise ServerClientError(f"Projects {missing} are not importing export {export.name!r}")
    export.imports = [imp for imp in export.imports if imp.project.name.lower() not in names]


async def remove_exported_fleets(export: ExportModel, names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise ServerClientError("Some fleets are listed for removal more than once")
    existing = {ef.fleet.name for ef in export.exported_fleets}
    if missing := set(names) - existing:
        raise ServerClientError(f"Fleets {missing} are not exported by export {export.name!r}")
    export.exported_fleets = [ef for ef in export.exported_fleets if ef.fleet.name not in names]


async def delete_export(session: AsyncSession, project: ProjectModel, name: str) -> None:
    async with get_export_model_by_name_for_update(session, project, name) as export:
        if export is None:
            raise ResourceNotExistsError(f"Export {name!r} not found in project {project.name!r}")
        await session.delete(export)
        await session.commit()


async def list_exports(session: AsyncSession, project: ProjectModel) -> list[Export]:
    res = await session.execute(
        select(ExportModel)
        .where(ExportModel.project == project)
        .options(
            selectinload(
                ExportModel.imports.and_(ImportModel.project.has(ProjectModel.deleted == False))
            )
            .joinedload(ImportModel.project)
            .load_only(ProjectModel.name),
            selectinload(
                ExportModel.exported_fleets.and_(
                    ExportedFleetModel.fleet.has(FleetModel.deleted == False)
                )
            )
            .joinedload(ExportedFleetModel.fleet)
            .load_only(FleetModel.name),
        )
        .order_by(ExportModel.created_at.desc())
    )
    exports = res.scalars().all()
    return [export_model_to_export(export) for export in exports]


def export_model_to_export(export_model: ExportModel) -> Export:
    return Export(
        id=export_model.id,
        name=export_model.name,
        imports=[
            ExportImport(
                project_name=import_model.project.name,
            )
            for import_model in export_model.imports
        ],
        exported_fleets=[
            ExportedFleet(
                id=exported_fleet_model.fleet.id,
                name=exported_fleet_model.fleet.name,
            )
            for exported_fleet_model in export_model.exported_fleets
        ],
    )
