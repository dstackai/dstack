import logging

from dstack._internal.core.models.backends.base import BackendType
from dstack.api.server._backends import BackendsAPIClient
from tests.api.common import RequestRecorder

AWS_CONFIG_PAYLOAD = {
    "type": "aws",
    "regions": ["eu-west-1"],
    "creds": {"type": "access_key", "access_key": "key", "secret_key": "secret"},
}


class TestBackendsAPIClientConfigInfo:
    def test_renders_backend_type_value_in_path(self):
        recorder = RequestRecorder(AWS_CONFIG_PAYLOAD)
        client = BackendsAPIClient(_request=recorder, _logger=logging.getLogger("test"))

        result = client.config_info("main", BackendType.AWS)

        assert recorder.last_path == "/api/project/main/backends/aws/config_info"
        assert result.type == "aws"
