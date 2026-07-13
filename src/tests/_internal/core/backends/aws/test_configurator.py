from unittest.mock import patch

import pytest

from dstack._internal.core.backends.aws.configurator import AWSConfigurator
from dstack._internal.core.backends.aws.models import AWSAccessKeyCreds, AWSBackendConfigWithCreds
from dstack._internal.core.errors import (
    BackendAuthError,
    BackendInvalidCredentialsError,
    ServerClientError,
)


class TestAWSConfigurator:
    def test_validate_config_valid(self):
        config = AWSBackendConfigWithCreds(
            creds=AWSAccessKeyCreds(access_key="valid", secret_key="valid"), regions=["us-west-1"]
        )
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnets_ids_or_error"),
        ):
            AWSConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = AWSBackendConfigWithCreds(
            creds=AWSAccessKeyCreds(access_key="invalid", secret_key="invalid"),
            regions=["us-west-1"],
        )
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate") as authenticate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            authenticate_mock.side_effect = BackendAuthError()
            AWSConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "access_key"], ["creds", "secret_key"]]

    def test_validate_config_security_group_name_and_ids_together(self):
        # Combining `security_group_name` (cross-region catch-all) with a per-region
        # `security_group_ids` map is supported and must not raise at validation time.
        config = AWSBackendConfigWithCreds(
            creds=AWSAccessKeyCreds(access_key="valid", secret_key="valid"),
            regions=["us-east-1", "us-west-1"],
            security_group_name="my-sg",
            security_group_ids={"us-east-1": "sg-123"},
        )
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnets_ids_or_error"),
        ):
            AWSConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_security_group_ids_unknown_region_raises(self):
        config = AWSBackendConfigWithCreds(
            creds=AWSAccessKeyCreds(access_key="valid", secret_key="valid"),
            regions=["us-east-1"],
            security_group_ids={"us-east1": "sg-123"},
        )
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnets_ids_or_error"),
            pytest.raises(ServerClientError) as exc_info,
        ):
            AWSConfigurator().validate_config(config, default_creds_enabled=True)
        assert "us-east1" in str(exc_info.value)

    def test_validate_config_security_group_ids_known_region_passes(self):
        config = AWSBackendConfigWithCreds(
            creds=AWSAccessKeyCreds(access_key="valid", secret_key="valid"),
            regions=["us-east-1"],
            security_group_ids={"us-east-1": "sg-123"},
        )
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnets_ids_or_error"),
        ):
            AWSConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_security_group_ids_default_regions_passes(self):
        # `regions` unset -> validated against DEFAULT_REGIONS.
        config = AWSBackendConfigWithCreds(
            creds=AWSAccessKeyCreds(access_key="valid", secret_key="valid"),
            security_group_ids={"us-east-1": "sg-123"},
        )
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnets_ids_or_error"),
        ):
            AWSConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_security_group_ids_partial_coverage_passes(self):
        # Partial coverage is intentional (falls back to name/auto-create); must not raise.
        config = AWSBackendConfigWithCreds(
            creds=AWSAccessKeyCreds(access_key="valid", secret_key="valid"),
            regions=["us-east-1", "us-west-1"],
            security_group_ids={"us-east-1": "sg-123"},
        )
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnets_ids_or_error"),
        ):
            AWSConfigurator().validate_config(config, default_creds_enabled=True)
