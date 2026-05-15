from typing import Optional

from kubernetes.client.api_client import ApiClient as _BaseApiClient
from kubernetes.client.configuration import Configuration as _ClientConfiguration
from kubernetes.client.exceptions import ApiException
from kubernetes.config import load_kube_config_from_dict
from urllib3.exceptions import HTTPError

# 30 * 2 (original request + 1 retry) = 60 seconds total
DEFAULT_REQUEST_TIMEOUT = 30
DEFAULT_RETRIES = 1


API_CLIENT_EXCEPTIONS: tuple[type[Exception], ...] = (HTTPError, ApiException)


class ApiClient(_BaseApiClient):
    def __init__(self, *, configuration: _ClientConfiguration, request_timeout: int) -> None:
        self.__request_timeout = request_timeout
        super().__init__(configuration=configuration)

    def request(self, *args, **kwargs):
        if kwargs.get("_request_timeout") is None:
            kwargs["_request_timeout"] = self.__request_timeout
        return super().request(*args, **kwargs)  # pyright: ignore[reportAttributeAccessIssue]


def get_api_client_from_kubeconfig_dict(
    kubeconfig_dict: dict,
    *,
    context: str,
    request_timeout: Optional[int] = None,
    retries: Optional[int] = None,
) -> ApiClient:
    if request_timeout is None:
        request_timeout = DEFAULT_REQUEST_TIMEOUT
    if retries is None:
        retries = DEFAULT_RETRIES
    client_configuration = _ClientConfiguration()
    client_configuration.retries = retries  # pyright: ignore[reportAttributeAccessIssue]
    load_kube_config_from_dict(
        config_dict=kubeconfig_dict,
        context=context,
        client_configuration=client_configuration,
    )
    return ApiClient(configuration=client_configuration, request_timeout=request_timeout)
