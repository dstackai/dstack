import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from dstack._internal.server import settings
from dstack._internal.server.models import EndpointModel
from dstack._internal.server.services.endpoints.agent.report import AgentFinalReport
from dstack._internal.server.services.pipelines import PipelineHinterProtocol


@dataclass(frozen=True)
class AgentPlan:
    model: str


@dataclass(frozen=True)
class AgentProvisioningResult:
    run_id: Optional[uuid.UUID] = None
    run_name: Optional[str] = None
    submitted_run_ids: tuple[uuid.UUID, ...] = ()
    submitted_run_names: tuple[str, ...] = ()
    error: Optional[str] = None
    final_report: Optional[AgentFinalReport] = None
    in_progress: bool = False


class AgentService(ABC):
    @abstractmethod
    def is_enabled(self) -> bool:
        pass

    @abstractmethod
    def get_plan(self) -> AgentPlan:
        pass

    @abstractmethod
    async def provision_endpoint(
        self,
        endpoint_model: EndpointModel,
        pipeline_hinter: PipelineHinterProtocol,
    ) -> AgentProvisioningResult:
        pass

    async def abort_endpoint(self, endpoint_model: EndpointModel) -> bool:
        return True


class DisabledAgentService(AgentService):
    def __init__(self, reason: Optional[str] = None) -> None:
        self._reason = reason

    def is_enabled(self) -> bool:
        return False

    def get_plan(self) -> AgentPlan:
        return AgentPlan(model=settings.AGENT_ANTHROPIC_MODEL)

    async def provision_endpoint(
        self,
        endpoint_model: EndpointModel,
        pipeline_hinter: PipelineHinterProtocol,
    ) -> AgentProvisioningResult:
        return AgentProvisioningResult(error=self._reason or get_agent_unavailable_reason())


async def abort_agent_endpoint(endpoint_model: EndpointModel) -> bool:
    # Cancellation must work even if a new agent session cannot be started because
    # the API key or Claude executable is no longer configured.
    from dstack._internal.server.services.endpoints.agent.claude import ClaudeAgentService

    return await ClaudeAgentService().abort_endpoint(endpoint_model)


def get_agent_service() -> AgentService:
    if _has_claude_agent_auth():
        from dstack._internal.server.services.endpoints.agent.claude import (
            ClaudeAgentService,
            get_claude_agent_unavailable_reason,
        )

        unavailable_reason = get_claude_agent_unavailable_reason()
        if unavailable_reason is None:
            return ClaudeAgentService()
        return DisabledAgentService(reason=unavailable_reason)
    return DisabledAgentService(reason=get_agent_unavailable_reason())


def get_agent_unavailable_reason() -> Optional[str]:
    if not _has_claude_agent_auth():
        return "DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
    from dstack._internal.server.services.endpoints.agent.claude import (
        get_claude_agent_unavailable_reason,
    )

    return get_claude_agent_unavailable_reason()


def _has_claude_agent_auth() -> bool:
    return bool(settings.AGENT_ANTHROPIC_API_KEY or settings.AGENT_CLAUDE_USE_EXISTING_AUTH)
