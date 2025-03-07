from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.backends.vastai.models import AnyVastAICreds, VastAIStoredConfig


class VastAIConfig(VastAIStoredConfig, BackendConfig):
    creds: AnyVastAICreds
