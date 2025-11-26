import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.events import Event, EventTarget, EventTargetType
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server import settings
from dstack._internal.server.models import (
    EventModel,
    EventTargetModel,
    FleetModel,
    InstanceModel,
    JobModel,
    MemberModel,
    ProjectModel,
    RunModel,
    UserModel,
)
from dstack._internal.utils.common import get_current_datetime


class SystemActor:
    pass


@dataclass
class UserActor:
    user_id: uuid.UUID


AnyActor = Union[SystemActor, UserActor]


@dataclass(
    frozen=True,  # to enforce the __post_init__ invariant
)
class Target:
    """
    Target specification for event emission.

    **NOTE**: Prefer using `Target.from_model` to create `Target` instances,
    unless you don't have a complete model available.
    """

    type: EventTargetType
    project_id: Optional[uuid.UUID]
    id: uuid.UUID
    name: str

    def __post_init__(self):
        if self.type == EventTargetType.USER and self.project_id is not None:
            raise ValueError("User target cannot have project_id")
        if self.type != EventTargetType.USER and self.project_id is None:
            raise ValueError(f"{self.type} target must have project_id")
        if self.type == EventTargetType.PROJECT and self.id != self.project_id:
            raise ValueError("Project target id must be equal to project_id")

    @staticmethod
    def from_model(
        model: Union[
            FleetModel,
            InstanceModel,
            JobModel,
            ProjectModel,
            RunModel,
            UserModel,
        ],
    ) -> "Target":
        if isinstance(model, FleetModel):
            return Target(
                type=EventTargetType.FLEET,
                project_id=model.project_id or model.project.id,
                id=model.id,
                name=model.name,
            )
        if isinstance(model, InstanceModel):
            return Target(
                type=EventTargetType.INSTANCE,
                project_id=model.project_id or model.project.id,
                id=model.id,
                name=model.name,
            )
        if isinstance(model, JobModel):
            return Target(
                type=EventTargetType.JOB,
                project_id=model.project_id or model.project.id,
                id=model.id,
                name=model.job_name,
            )
        if isinstance(model, ProjectModel):
            return Target(
                type=EventTargetType.PROJECT,
                project_id=model.id,
                id=model.id,
                name=model.name,
            )
        if isinstance(model, RunModel):
            return Target(
                type=EventTargetType.RUN,
                project_id=model.project_id or model.project.id,
                id=model.id,
                name=model.run_name,
            )
        if isinstance(model, UserModel):
            return Target(
                type=EventTargetType.USER,
                project_id=None,
                id=model.id,
                name=model.name,
            )
        raise ValueError(f"Unsupported model type: {type(model)}")


def emit(session: AsyncSession, message: str, actor: AnyActor, targets: Iterable[Target]) -> None:
    # TODO: docstring + best practices
    # TODO: log each event
    if settings.SERVER_EVENTS_TTL_SECONDS <= 0:
        return
    event = EventModel(
        message=message,
        actor_user_id=actor.user_id if isinstance(actor, UserActor) else None,
        recorded_at=get_current_datetime(),
        targets=[],
    )
    for target in targets:
        event.targets.append(
            EventTargetModel(
                entity_type=target.type,
                entity_project_id=target.project_id,
                entity_id=target.id,
                entity_name=target.name,
            )
        )
    if not event.targets:
        raise ValueError("At least one target must be specified for an event")
    session.add(event)


async def list_events(
    session: AsyncSession,
    user: UserModel,  # the user requesting the events
    target_projects: Optional[list[uuid.UUID]],
    target_users: Optional[list[uuid.UUID]],
    target_fleets: Optional[list[uuid.UUID]],
    target_instances: Optional[list[uuid.UUID]],
    target_runs: Optional[list[uuid.UUID]],
    target_jobs: Optional[list[uuid.UUID]],
    within_projects: Optional[list[uuid.UUID]],
    within_fleets: Optional[list[uuid.UUID]],
    within_runs: Optional[list[uuid.UUID]],
    include_target_types: Optional[list[EventTargetType]],
    actors: Optional[list[Optional[uuid.UUID]]],
    prev_recorded_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> list[Event]:
    filters = []
    if user.global_role != GlobalRole.ADMIN:
        filters.append(
            or_(
                EventTargetModel.entity_project_id.in_(
                    select(MemberModel.project_id).where(MemberModel.user_id == user.id)
                ),
                and_(
                    EventTargetModel.entity_project_id.is_(None),
                    EventTargetModel.entity_type == EventTargetType.USER,
                    EventTargetModel.entity_id == user.id,
                ),
            )
        )
    if target_projects is not None:
        filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.PROJECT,
                EventTargetModel.entity_id.in_(target_projects),
            )
        )
    if target_users is not None:
        filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.USER,
                EventTargetModel.entity_id.in_(target_users),
            )
        )
    if target_fleets is not None:
        filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.FLEET,
                EventTargetModel.entity_id.in_(target_fleets),
            )
        )
    if target_instances is not None:
        filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.INSTANCE,
                EventTargetModel.entity_id.in_(target_instances),
            )
        )
    if target_runs is not None:
        filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.RUN,
                EventTargetModel.entity_id.in_(target_runs),
            )
        )
    if target_jobs is not None:
        filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.JOB,
                EventTargetModel.entity_id.in_(target_jobs),
            )
        )
    if within_projects is not None:
        filters.append(EventTargetModel.entity_project_id.in_(within_projects))
    if within_fleets is not None:
        filters.append(
            or_(
                and_(
                    EventTargetModel.entity_type == EventTargetType.FLEET,
                    EventTargetModel.entity_id.in_(within_fleets),
                ),
                and_(
                    EventTargetModel.entity_type == EventTargetType.INSTANCE,
                    EventTargetModel.entity_id.in_(
                        select(InstanceModel.id).where(InstanceModel.fleet_id.in_(within_fleets))
                    ),
                ),
            )
        )
    if within_runs is not None:
        filters.append(
            or_(
                and_(
                    EventTargetModel.entity_type == EventTargetType.RUN,
                    EventTargetModel.entity_id.in_(within_runs),
                ),
                and_(
                    EventTargetModel.entity_type == EventTargetType.JOB,
                    EventTargetModel.entity_id.in_(
                        select(JobModel.id).where(JobModel.run_id.in_(within_runs))
                    ),
                ),
            )
        )
    if include_target_types is not None:
        filters.append(EventTargetModel.entity_type.in_(include_target_types))
    if actors is not None:
        filters.append(
            or_(
                EventModel.actor_user_id.is_(None) if None in actors else False,
                EventModel.actor_user_id.in_(
                    [actor_id for actor_id in actors if actor_id is not None]
                ),
            )
        )
    if prev_recorded_at is not None:
        if ascending:
            if prev_id is None:
                filters.append(EventModel.recorded_at > prev_recorded_at)
            else:
                filters.append(
                    or_(
                        EventModel.recorded_at > prev_recorded_at,
                        and_(EventModel.recorded_at == prev_recorded_at, EventModel.id < prev_id),
                    )
                )
        else:
            if prev_id is None:
                filters.append(EventModel.recorded_at < prev_recorded_at)
            else:
                filters.append(
                    or_(
                        EventModel.recorded_at < prev_recorded_at,
                        and_(EventModel.recorded_at == prev_recorded_at, EventModel.id > prev_id),
                    )
                )
    order_by = (EventModel.recorded_at.desc(), EventModel.id)
    if ascending:
        order_by = (EventModel.recorded_at.asc(), EventModel.id.desc())
    query = (
        select(EventModel)
        .order_by(*order_by)
        .limit(limit)
        .options(
            joinedload(EventModel.targets),
            joinedload(EventModel.user).load_only(UserModel.name),
        )
    )
    if filters:
        # Apply filters in a subquery, since it requires joining events with targets.
        # Can't join in the outer query, as it results in LIMIT being applied to targets
        # instead of events.
        event_ids_subquery = (
            select(EventModel.id).join(EventModel.targets).where(*filters).distinct()
        )
        query = query.where(EventModel.id.in_(event_ids_subquery))
    res = await session.execute(query)
    event_models = res.unique().scalars().all()
    return list(map(event_model_to_event, event_models))


def event_model_to_event(event_model: EventModel) -> Event:
    targets = [
        EventTarget(
            type=target.entity_type,
            project_id=target.entity_project_id,
            id=target.entity_id,
            name=target.entity_name,
        )
        for target in event_model.targets
    ]

    return Event(
        id=event_model.id,
        message=event_model.message,
        recorded_at=event_model.recorded_at,
        actor_user_id=event_model.actor_user_id,
        actor_user=event_model.user.name if event_model.user else None,
        targets=targets,
    )
