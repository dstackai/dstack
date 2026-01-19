import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union

from sqlalchemy import and_, exists, or_, select
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
from dstack._internal.server.services.logging import fmt_entity
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class SystemActor:
    """Represents the system as the actor of an event"""

    def fmt(self) -> str:
        return "system"


@dataclass
class UserActor:
    """
    Represents a user as the actor of an event.

    **NOTE**: Prefer using `UserActor.from_user` to create `UserActor` instances,
    unless you don't have a complete `UserModel` available.
    """

    user_id: uuid.UUID
    user_name: str

    @staticmethod
    def from_user(user: UserModel) -> "UserActor":
        return UserActor(user_id=user.id, user_name=user.name)

    def fmt(self) -> str:
        return fmt_entity("user", self.user_id, self.user_name)


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

    def fmt(self) -> str:
        return fmt_entity(self.type.value, self.id, self.name)


def emit(session: AsyncSession, message: str, actor: AnyActor, targets: list[Target]) -> None:
    """
    Emit an event - add it to the current session without committing.

    Usage guidelines:
    - Message:
        - Use past tense - events should describe completed actions.
          Bad: "Creating project"
          Good: "Project created"
        - Do not duplicate target and actor names in the message.
          Bad: "User John created project MyProject"
          Good: "Project created"
    - Actor:
        - Pass `UserActor` for events about user actions, e.g., in API handlers.
        - Pass `SystemActor` for system-generated events, e.g., in background jobs.
    - Targets:
        - Link the event to one or more entities affected by it.
          E.g., for a "Job assigned to instance" event, link it to the job and the instance.
        - Do not link the event to parent entities of the affected entities.
          E.g., the "Instance created" event should be linked to the instance only,
          not to the fleet or project. Transitive relationships with parent entities
          are inferred automatically when listing events using the within_* filters.
        - **Important**: If linking the event to multiple targets with different access scopes
          (e.g., entities in different projects, or different users), ensure that this does not
          leak sensitive information. If a user has access to at least one of the targets,
          they will see the entire event with all targets. If this is not desired,
          consider emitting multiple separate events instead.
    """
    if not targets:
        raise ValueError("At least one target must be specified")
    message = message.strip().rstrip(".").replace("\n", " ")
    if not message:
        raise ValueError("Message cannot be empty")

    logger.info(
        "Emitting event: %s. Event targets: %s. Actor: %s",
        message,
        ", ".join(target.fmt() for target in targets),
        actor.fmt(),
    )

    if settings.SERVER_EVENTS_TTL_SECONDS <= 0:
        return
    event = EventModel(
        id=uuid.uuid4(),
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
    target_filters = []
    if user.global_role != GlobalRole.ADMIN:
        query = select(MemberModel.project_id).where(MemberModel.user_id == user.id)
        res = await session.execute(query)
        # In Postgres, fetching project IDs separately is orders of magnitude faster
        # than using a subquery.
        project_ids = list(res.unique().scalars().all())
        target_filters.append(
            or_(
                EventTargetModel.entity_project_id.in_(project_ids),
                and_(
                    EventTargetModel.entity_project_id.is_(None),
                    EventTargetModel.entity_type == EventTargetType.USER,
                    EventTargetModel.entity_id == user.id,
                ),
            )
        )
    if target_projects is not None:
        target_filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.PROJECT,
                EventTargetModel.entity_id.in_(target_projects),
            )
        )
    if target_users is not None:
        target_filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.USER,
                EventTargetModel.entity_id.in_(target_users),
            )
        )
    if target_fleets is not None:
        target_filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.FLEET,
                EventTargetModel.entity_id.in_(target_fleets),
            )
        )
    if target_instances is not None:
        target_filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.INSTANCE,
                EventTargetModel.entity_id.in_(target_instances),
            )
        )
    if target_runs is not None:
        target_filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.RUN,
                EventTargetModel.entity_id.in_(target_runs),
            )
        )
    if target_jobs is not None:
        target_filters.append(
            and_(
                EventTargetModel.entity_type == EventTargetType.JOB,
                EventTargetModel.entity_id.in_(target_jobs),
            )
        )
    if within_projects is not None:
        target_filters.append(EventTargetModel.entity_project_id.in_(within_projects))
    if within_fleets is not None:
        query = select(InstanceModel.id).where(InstanceModel.fleet_id.in_(within_fleets))
        res = await session.execute(query)
        # In Postgres, fetching instance IDs separately is orders of magnitude faster
        # than using a subquery.
        instance_ids = list(res.unique().scalars().all())
        target_filters.append(
            or_(
                and_(
                    EventTargetModel.entity_type == EventTargetType.FLEET,
                    EventTargetModel.entity_id.in_(within_fleets),
                ),
                and_(
                    EventTargetModel.entity_type == EventTargetType.INSTANCE,
                    EventTargetModel.entity_id.in_(instance_ids),
                ),
            )
        )
    if within_runs is not None:
        query = select(JobModel.id).where(JobModel.run_id.in_(within_runs))
        res = await session.execute(query)
        # In Postgres, fetching job IDs separately is orders of magnitude faster
        # than using a subquery.
        job_ids = list(res.unique().scalars().all())
        target_filters.append(
            or_(
                and_(
                    EventTargetModel.entity_type == EventTargetType.RUN,
                    EventTargetModel.entity_id.in_(within_runs),
                ),
                and_(
                    EventTargetModel.entity_type == EventTargetType.JOB,
                    EventTargetModel.entity_id.in_(job_ids),
                ),
            )
        )
    if include_target_types is not None:
        target_filters.append(EventTargetModel.entity_type.in_(include_target_types))

    event_filters = []
    if actors is not None:
        event_filters.append(
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
                event_filters.append(EventModel.recorded_at > prev_recorded_at)
            else:
                event_filters.append(
                    or_(
                        EventModel.recorded_at > prev_recorded_at,
                        and_(EventModel.recorded_at == prev_recorded_at, EventModel.id < prev_id),
                    )
                )
        else:
            if prev_id is None:
                event_filters.append(EventModel.recorded_at < prev_recorded_at)
            else:
                event_filters.append(
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
            (
                joinedload(EventModel.targets)
                .joinedload(EventTargetModel.entity_project)
                .load_only(ProjectModel.name, ProjectModel.original_name, ProjectModel.deleted)
                .noload(ProjectModel.owner)
            ),
            joinedload(EventModel.actor_user).load_only(
                UserModel.name, UserModel.original_name, UserModel.deleted
            ),
        )
    )
    if event_filters:
        query = query.where(*event_filters)
    if target_filters:
        query = query.where(
            exists().where(
                and_(
                    EventTargetModel.event_id == EventModel.id,
                    *target_filters,
                )
            )
        )
    res = await session.execute(query)
    event_models = res.unique().scalars().all()
    return list(map(event_model_to_event, event_models))


def event_target_model_to_event_target(model: EventTargetModel) -> EventTarget:
    project_name = None
    is_project_deleted = None
    if model.entity_project is not None:
        project_name = model.entity_project.name
        is_project_deleted = model.entity_project.deleted
        if is_project_deleted and model.entity_project.original_name is not None:
            project_name = model.entity_project.original_name
    return EventTarget(
        type=model.entity_type.value,
        project_id=model.entity_project_id,
        project_name=project_name,
        is_project_deleted=is_project_deleted,
        id=model.entity_id,
        name=model.entity_name,
    )


def event_model_to_event(event_model: EventModel) -> Event:
    actor_user_name = None
    is_actor_user_deleted = None
    if event_model.actor_user is not None:
        actor_user_name = event_model.actor_user.name
        is_actor_user_deleted = event_model.actor_user.deleted
        if is_actor_user_deleted and event_model.actor_user.original_name is not None:
            actor_user_name = event_model.actor_user.original_name
    targets = list(map(event_target_model_to_event_target, event_model.targets))
    return Event(
        id=event_model.id,
        message=event_model.message,
        recorded_at=event_model.recorded_at,
        actor_user_id=event_model.actor_user_id,
        actor_user=actor_user_name,
        is_actor_user_deleted=is_actor_user_deleted,
        targets=targets,
    )
