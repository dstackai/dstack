from typing import Protocol

from fastapi import Request


class PipelineHinterProtocol(Protocol):
    def hint_fetch(self, model_name: str) -> None:
        """
        Pass `Model.__name__` to hint replica's pipelines to fetch the model's items ASAP.
        """
        pass


class _NoopPipelineHinter:
    def hint_fetch(self, model_name: str) -> None:
        pass


_noop_pipeline_hinter = _NoopPipelineHinter()


def get_pipeline_hinter(request: Request) -> PipelineHinterProtocol:
    """
    Returns pipeline hinter that allows hinting replica's pipelines that there are new items for processing.
    This can reduce processing latency if the processing happens rarely.
    """
    pipeline_manager = getattr(request.app.state, "pipeline_manager", None)
    if pipeline_manager is None:
        return _noop_pipeline_hinter
    return pipeline_manager.hinter
