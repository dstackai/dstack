from unittest.mock import AsyncMock, Mock

import pytest
from nebius.api.nebius.capacity.v1 import ListResourceAdviceResponse, ResourceAdvice
from nebius.api.nebius.common.v1 import ResourceMetadata

from dstack._internal.core.backends.nebius import resources
from dstack._internal.core.backends.nebius.models import NebiusServiceAccountCreds


def test_make_sdk_sets_user_agent_prefix(mocker):
    sdk_cls = mocker.patch.object(resources, "SDK")
    mocker.patch.object(resources, "__version__", "1.2.3")
    creds = NebiusServiceAccountCreds(
        service_account_id="service-account-id",
        public_key_id="public-key-id",
        private_key_content="private-key",
    )

    resources.make_sdk(creds)

    assert sdk_cls.call_args.kwargs["user_agent_prefix"] == "dstack/1.2.3"


class TestListResourceAdvice:
    def test_lists_all_pages(self, mocker):
        sdk = Mock()
        client_cls = mocker.patch.object(resources, "ResourceAdviceServiceClient")
        first = ResourceAdvice(metadata=ResourceMetadata(id="advice-1"))
        second = ResourceAdvice(metadata=ResourceMetadata(id="advice-2"))
        client_cls.return_value.list = AsyncMock(
            side_effect=[
                ListResourceAdviceResponse(items=[first], next_page_token="page-2"),
                ListResourceAdviceResponse(items=[second]),
            ]
        )

        advice = resources.list_resource_advice(sdk, "tenant-id")

        assert [item.metadata.id for item in advice] == ["advice-1", "advice-2"]
        client_cls.assert_called_once_with(sdk)
        calls = client_cls.return_value.list.call_args_list
        assert [call.args[0].page_token for call in calls] == ["", "page-2"]
        for call in calls:
            assert call.args[0].parent_id == "tenant-id"
            assert call.args[0].page_size == resources.LIST_PAGE_SIZE
            assert call.kwargs == {
                "timeout": resources.REQUEST_TIMEOUT,
                "auth_options": resources.REQUEST_AUTH_OPTIONS,
            }

    def test_does_not_return_partial_advice_on_failure(self, mocker):
        client = mocker.patch.object(resources, "ResourceAdviceServiceClient").return_value
        client.list = AsyncMock(
            side_effect=[
                ListResourceAdviceResponse(items=[ResourceAdvice()], next_page_token="page-2"),
                TimeoutError("capacity request timed out"),
            ]
        )

        with pytest.raises(TimeoutError):
            resources.list_resource_advice(Mock(), "tenant-id")
