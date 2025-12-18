from dstack._internal.core.models.auth import OAuthProviderInfo

_OAUTH_PROVIDERS: list[OAuthProviderInfo] = []


def register_provider(provider_info: OAuthProviderInfo):
    """
    Registers an OAuth2 provider supported on the server.
    If the provider is supported but not configured, it should be registered with `enabled=False`.
    """
    _OAUTH_PROVIDERS.append(provider_info)


def list_providers() -> list[OAuthProviderInfo]:
    return _OAUTH_PROVIDERS
