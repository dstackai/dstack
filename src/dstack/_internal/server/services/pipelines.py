from typing import Protocol

from fastapi import Request


class PipelineHinterProtocol(Protocol):
    def hint_fetch(self, model_name: str) -> None:
        """
        Pass `Model.__name__` to hint replica's pipelines to fetch the model's items ASAP.
        """
        pass


def get_pipeline_hinter(request: Request) -> PipelineHinterProtocol:
    """
    Returns pipeline hinter that allows hinting replica's pipelines that there are new items for processing.
    This can reduce processing latency if the processing happens rarely.
    """
    return request.app.state.pipeline_manager.hinter
