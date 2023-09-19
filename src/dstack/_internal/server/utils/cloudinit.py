import os
from typing import List, Optional

import yaml

import dstack.version as version


def get_cloud_config(commands: List[List[str]], authorized_keys: List[str], **kwargs) -> str:
    config = {
        "runcmd": commands,
        "ssh_authorized_keys": authorized_keys,
        **kwargs,
    }
    return "#cloud-config\n" + yaml.dump(config, default_flow_style=False)


def get_dstack_shim(build: str) -> List[str]:
    bucket = "dstack-runner-downloads-stgn"
    if version.__is_release__:
        bucket = "dstack-runner-downloads"

    return [
        f'sudo curl --output /usr/local/bin/dstack-shim "https://{bucket}.s3.eu-west-1.amazonaws.com/{build}/binaries/dstack-shim-linux-amd64"',
        "sudo chmod +x /usr/local/bin/dstack-shim",
    ]


def get_dstack_runner_version() -> str:
    if version.__is_release__:
        return version.__version__
    return os.environ.get("DSTACK_RUNNER_VERSION", None) or "latest"
