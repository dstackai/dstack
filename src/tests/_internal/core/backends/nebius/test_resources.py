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
