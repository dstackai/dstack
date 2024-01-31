import asyncio
import datetime
from functools import lru_cache
from typing import Dict, List, Tuple

from pydantic import BaseModel, ValidationError

from dstack.gateway.errors import GatewayError, NotFoundError
from dstack.gateway.openai.clients import ChatCompletionsClient
from dstack.gateway.openai.clients.openai import OpenAIChatCompletions
from dstack.gateway.openai.clients.tgi import TGIChatCompletions
from dstack.gateway.openai.models import OpenAIOptions, ServiceModel
from dstack.gateway.openai.schemas import Model
from dstack.gateway.schemas import Service
from dstack.gateway.services.persistent import get_persistent_state
from dstack.gateway.services.store import StoreSubscriber


class OpenAIStore(BaseModel, StoreSubscriber):
    """
    OpenAIStore keeps track of LLM models registered in the system and dispatches requests.
    Its internal state could be serialized to a file and restored from it using pydantic.
    """

    index: Dict[str, Dict[str, Dict[str, ServiceModel]]] = {}
    domain_index: Dict[str, Tuple[str, str, str]] = {}
    _lock: asyncio.Lock = asyncio.Lock()

    async def on_register(self, project: str, service: Service):
        if "openai" not in service.options:
            return
        try:
            model = OpenAIOptions.model_validate(service.options["openai"]).model
        except ValidationError as e:
            raise GatewayError(e)

        async with self._lock:
            if project not in self.index:
                self.index[project] = {}
            if model.type not in self.index[project]:
                self.index[project][model.type] = {}
            self.index[project][model.type][model.name] = ServiceModel(
                model=model,
                domain=service.public_domain,
                created=int(datetime.datetime.utcnow().timestamp()),
            )
            self.domain_index[service.public_domain] = (project, model.type, model.name)

    async def on_unregister(self, project: str, domain: str):
        async with self._lock:
            if domain not in self.domain_index or self.domain_index[domain][0] != project:
                return
            project, model_type, model_name = self.domain_index[domain]
            del self.domain_index[domain]
            del self.index[project][model_type][model_name]

    async def list_models(self, project: str) -> List[Model]:
        models = []
        async with self._lock:
            for model_type, type_models in self.index.get(project, {}).items():
                for model_name, service in type_models.items():
                    models.append(
                        Model(
                            id=model_name,
                            created=service.created,
                            owned_by=project,
                        )
                    )
        return models

    async def get_chat_client(self, project: str, model_name: str) -> ChatCompletionsClient:
        async with self._lock:
            if project not in self.index:
                raise NotFoundError(f"Project {project} not found")
            if "chat" not in self.index[project] or model_name not in self.index[project]["chat"]:
                raise NotFoundError(f"Model {model_name} not found")
            service = self.index[project]["chat"][model_name]
            if service.model.format == "tgi":
                return TGIChatCompletions(
                    base_url="http://localhost",
                    host=service.domain,
                    chat_template=service.model.chat_template,
                    eos_token=service.model.eos_token,
                )
            elif service.model.format == "openai":
                return OpenAIChatCompletions(
                    base_url=f"http://localhost/{service.model.prefix.lstrip('/')}",
                    host=service.domain,
                )
            else:
                raise GatewayError(f"Unsupported model format: {service.model.format}")


@lru_cache()
def get_store() -> OpenAIStore:
    return OpenAIStore.model_validate(get_persistent_state().get("openai", {}))
