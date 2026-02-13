from typing import Protocol

from fastapi import Request


class PipelineHinterProtocol(Protocol):
    def hint_fetch(self, model_name: str) -> None:
        pass


def get_pipeline_hinter(request: Request) -> PipelineHinterProtocol:
    return request.app.state.pipeline_manager.hinter
