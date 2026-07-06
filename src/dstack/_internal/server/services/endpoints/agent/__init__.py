import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from dstack._internal.core.models.endpoints import EndpointConfiguration
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


def get_agent_service() -> AgentService:
    if settings.AGENT_ANTHROPIC_API_KEY:
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
    if not settings.AGENT_ANTHROPIC_API_KEY:
        return "DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
    from dstack._internal.server.services.endpoints.agent.claude import (
        get_claude_agent_unavailable_reason,
    )

    return get_claude_agent_unavailable_reason()


def get_effective_max_agent_budget(
    configuration: EndpointConfiguration,
) -> Optional[float]:
    if configuration.max_agent_budget is not None:
        return configuration.max_agent_budget
    return settings.AGENT_ANTHROPIC_MAX_BUDGET
