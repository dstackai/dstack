import concurrent.futures
import json

import botocore.exceptions
from boto3.session import Session

from dstack._internal.core.backends.aws import auth, compute, resources
from dstack._internal.core.backends.aws.backend import AWSBackend
from dstack._internal.core.backends.aws.models import (
    AWSAccessKeyCreds,
    AWSBackendConfig,
    AWSBackendConfigWithCreds,
    AWSConfig,
    AWSCreds,
    AWSDefaultCreds,
    AWSStoredConfig,
)
from dstack._internal.core.backends.base.configurator import (
    TAGS_MAX_NUM,
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.errors import (
    BackendError,
    ServerClientError,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# where dstack OS images are published
REGIONS = [
    ("US East, N. Virginia", "us-east-1"),
    ("US East, Ohio", "us-east-2"),
    ("US West, N. California", "us-west-1"),
    ("US West, Oregon", "us-west-2"),
    ("Asia Pacific, Singapore", "ap-southeast-1"),
    ("Canada, Central", "ca-central-1"),
    ("Europe, Frankfurt", "eu-central-1"),
    ("Europe, Ireland", "eu-west-1"),
    ("Europe, London", "eu-west-2"),
    ("Europe, Paris", "eu-west-3"),
    ("Europe, Stockholm", "eu-north-1"),
]
REGION_VALUES = [r[1] for r in REGIONS]
DEFAULT_REGIONS = REGION_VALUES
MAIN_REGION = "us-east-1"


class AWSConfigurator(
    Configurator[
        AWSBackendConfig,
        AWSBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.AWS
    BACKEND_CLASS = AWSBackend

    def validate_config(self, config: AWSBackendConfigWithCreds, default_creds_enabled: bool):
        if isinstance(config.creds, AWSDefaultCreds) and not default_creds_enabled:
            raise_invalid_credentials_error(fields=[["creds"]])
        try:
            session = auth.authenticate(creds=config.creds, region=MAIN_REGION)
        except Exception:
            if isinstance(config.creds, AWSAccessKeyCreds):
                raise_invalid_credentials_error(
                    fields=[
                        ["creds", "access_key"],
                        ["creds", "secret_key"],
                    ]
                )
            else:
                raise_invalid_credentials_error(fields=[["creds"]])
        self._check_config_tags(config)
        self._check_config_iam_instance_profile(session, config)
        self._check_config_vpc(session, config)

    def create_backend(
        self, project_name: str, config: AWSBackendConfigWithCreds
    ) -> BackendRecord:
        if config.regions is None:
            config.regions = DEFAULT_REGIONS
        return BackendRecord(
            config=AWSStoredConfig(
                **AWSBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=AWSCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> AWSBackendConfigWithCreds:
        config = self._get_config(record)
        return AWSBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> AWSBackendConfig:
        config = self._get_config(record)
        return AWSBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> AWSBackend:
        config = self._get_config(record)
        return AWSBackend(config=config)

    def _get_config(self, record: BackendRecord) -> AWSConfig:
        return AWSConfig.__response__(
            **json.loads(record.config),
            creds=AWSCreds.parse_raw(record.auth).__root__,
        )

    def _check_config_tags(self, config: AWSBackendConfigWithCreds):
        if not config.tags:
            return
        if len(config.tags) > TAGS_MAX_NUM:
            raise ServerClientError(
                f"Maximum number of tags exceeded. Up to {TAGS_MAX_NUM} tags is allowed."
            )
        try:
            resources.validate_tags(config.tags)
        except BackendError as e:
            raise ServerClientError(e.args[0])

    def _check_config_iam_instance_profile(
        self, session: Session, config: AWSBackendConfigWithCreds
    ):
        if config.iam_instance_profile is None:
            return
        try:
            iam_client = session.client("iam")
            iam_client.get_instance_profile(InstanceProfileName=config.iam_instance_profile)
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchEntity":
                raise ServerClientError(
                    f"IAM instance profile {config.iam_instance_profile} not found"
                )
            logger.exception(
                "Got botocore.exceptions.ClientError when checking iam_instance_profile"
            )
            raise ServerClientError(
                f"Failed to check IAM instance profile {config.iam_instance_profile}"
            )
        except Exception:
            logger.exception("Got exception when checking iam_instance_profile")
            raise ServerClientError(
                f"Failed to check IAM instance profile {config.iam_instance_profile}"
            )

    def _check_config_vpc(self, session: Session, config: AWSBackendConfigWithCreds):
        allocate_public_ip = config.public_ips if config.public_ips is not None else True
        use_default_vpcs = config.default_vpcs if config.default_vpcs is not None else True
        if config.vpc_name is not None and config.vpc_ids is not None:
            raise ServerClientError(msg="Only one of `vpc_name` and `vpc_ids` can be specified")
        if not use_default_vpcs and config.vpc_name is None and config.vpc_ids is None:
            raise ServerClientError(
                msg="`vpc_name` or `vpc_ids` must be specified if `default_vpcs: false`."
            )
        regions = config.regions
        if regions is None:
            regions = DEFAULT_REGIONS
        if config.vpc_ids is not None and not use_default_vpcs:
            vpc_ids_regions = list(config.vpc_ids.keys())
            not_configured_regions = [r for r in regions if r not in vpc_ids_regions]
            if len(not_configured_regions) > 0:
                if config.regions is None:
                    raise ServerClientError(
                        f"`vpc_ids` not configured for regions {not_configured_regions}. "
                        "Configure `vpc_ids` for all regions or specify `regions`."
                    )
                raise ServerClientError(
                    f"`vpc_ids` not configured for regions {not_configured_regions}. "
                    "Configure `vpc_ids` for all regions specified in `regions`."
                )
        # The number of workers should be >= the number of regions
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = []
            for region in regions:
                ec2_client = session.client("ec2", region_name=region)
                future = executor.submit(
                    compute.get_vpc_id_subnet_id_or_error,
                    ec2_client=ec2_client,
                    config=AWSConfig.parse_obj(config),
                    region=region,
                    allocate_public_ip=allocate_public_ip,
                )
                futures.append(future)
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except BackendError as e:
                    raise ServerClientError(e.args[0])
