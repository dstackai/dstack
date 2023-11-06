from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.vastai import AnyVastAICreds, VastAIStoredConfig


class VastAIConfig(VastAIStoredConfig, BackendConfig):
    creds: AnyVastAICreds
