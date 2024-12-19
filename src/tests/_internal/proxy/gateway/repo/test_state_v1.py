from datetime import datetime
from pathlib import Path

import pytest

from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.proxy.gateway.models import ACMESettings, GlobalProxyConfig, ModelEntrypoint
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.repo.state_v1 import migrate_from_state_v1
from dstack._internal.proxy.lib.models import (
    ChatModel,
    OpenAIChatModelFormat,
    Project,
    Replica,
    Service,
    TGIChatModelFormat,
)
from dstack._internal.proxy.lib.testing.common import make_project

SAMPLE_STATE_V1 = """
{
    "store": {
        "services": {
            "40023ad58d624702b58fbda38489239e": {
                "id": "40023ad58d624702b58fbda38489239e",
                "domain": "run-1.proj-1.gateway.test",
                "https": true,
                "auth": true,
                "client_max_body_size": 67108864,
                "options": {
                    "openai": {
                        "model": {
                            "type": "chat",
                            "name": "model/1",
                            "format": "openai",
                            "prefix": "/v1"
                        }
                    }
                },
                "replicas": [
                    {
                        "id": "b894c006be5d4034bd751e57af0b4561",
                        "app_port": 11434,
                        "ssh_host": "root@10.0.0.1",
                        "ssh_port": 11165,
                        "ssh_jump_host": null,
                        "ssh_jump_port": null,
                        "ssh_tunnel": {
                            "temp_dir": "/tmp/tmp9y9zncvb",
                            "start_cmd": [],
                            "exit_cmd": [],
                            "check_cmd": []
                        }
                    }
                ]
            },
            "c41cac40726b403692ca63292b4a3af8": {
                "id": "c41cac40726b403692ca63292b4a3af8",
                "domain": "run-2.proj-2.gateway.test",
                "https": true,
                "auth": false,
                "client_max_body_size": 67108864,
                "options": {},
                "replicas": [
                    {
                        "id": "4aa53ef5759d400ea41e0ec6a34354ed",
                        "app_port": 8000,
                        "ssh_host": "root@localhost",
                        "ssh_port": 10022,
                        "ssh_jump_host": "root@10.0.0.2",
                        "ssh_jump_port": 22,
                        "ssh_tunnel": {
                            "temp_dir": "/tmp/tmprz98c6mi",
                            "start_cmd": [],
                            "exit_cmd": [],
                            "check_cmd": []
                        }
                    },
                    {
                        "id": "f1e60fedfc5a46f791f26a042b57b9f4",
                        "app_port": 8000,
                        "ssh_host": "root@localhost",
                        "ssh_port": 10022,
                        "ssh_jump_host": "root@10.0.0.3",
                        "ssh_jump_port": 22,
                        "ssh_tunnel": {
                            "temp_dir": "/tmp/tmps9v5tsq_",
                            "start_cmd": [],
                            "exit_cmd": [],
                            "check_cmd": []
                        }
                    }
                ]
            },
            "bcaa6ce30f2a4ffab279a44ef696ec7c": {
                "id": "bcaa6ce30f2a4ffab279a44ef696ec7c",
                "domain": "run-3.proj-2.gateway.test",
                "https": true,
                "auth": true,
                "client_max_body_size": 67108864,
                "options": {
                    "openai": {
                        "model": {
                            "type": "chat",
                            "name": "model/2",
                            "format": "tgi",
                            "chat_template": "test chat template",
                            "eos_token": "<|eot_id|>"
                        }
                    }
                },
                "replicas": [
                    {
                        "id": "16fc0bd438d747bba810cef00bc137de",
                        "app_port": 80,
                        "ssh_host": "root@localhost",
                        "ssh_port": 10022,
                        "ssh_jump_host": "root@10.0.0.4",
                        "ssh_jump_port": 22,
                        "ssh_tunnel": {
                            "temp_dir": "/tmp/tmpzyx08k1s",
                            "start_cmd": [],
                            "exit_cmd": [],
                            "check_cmd": []
                        }
                    }
                ]
            }
        },
        "projects": {
            "proj-2": [
                "bcaa6ce30f2a4ffab279a44ef696ec7c",
                "c41cac40726b403692ca63292b4a3af8"
            ],
            "proj-1": [
                "40023ad58d624702b58fbda38489239e"
            ]
        },
        "entrypoints": {
            "gateway.proj-2.gateway.test": [
                "proj-2",
                "openai"
            ],
            "gateway.proj-1.gateway.test": [
                "proj-1",
                "openai"
            ]
        },
        "nginx": {
            "configs": {
                "443-gateway.proj-2.gateway.test.conf": {
                    "type": "entrypoint",
                    "domain": "gateway.proj-2.gateway.test",
                    "https": true,
                    "proxy_path": "/api/openai/proj-2"
                },
                "443-gateway.proj-1.gateway.test.conf": {
                    "type": "entrypoint",
                    "domain": "gateway.proj-1.gateway.test",
                    "https": true,
                    "proxy_path": "/api/openai/proj-1"
                },
                "443-run-1.proj-1.gateway.test.conf": {
                    "type": "service",
                    "domain": "run-1.proj-1.gateway.test",
                    "https": true,
                    "project": "proj-1",
                    "service_id": "40023ad58d624702b58fbda38489239e",
                    "auth": true,
                    "client_max_body_size": 67108864,
                    "servers": {
                        "b894c006be5d4034bd751e57af0b4561": "unix:/tmp/tmp9y9zncvb/sock"
                    }
                },
                "443-run-2.proj-2.gateway.test.conf": {
                    "type": "service",
                    "domain": "run-2.proj-2.gateway.test",
                    "https": true,
                    "project": "proj-2",
                    "service_id": "c41cac40726b403692ca63292b4a3af8",
                    "auth": false,
                    "client_max_body_size": 67108864,
                    "servers": {
                        "4aa53ef5759d400ea41e0ec6a34354ed": "unix:/tmp/tmprz98c6mi/sock",
                        "f1e60fedfc5a46f791f26a042b57b9f4": "unix:/tmp/tmps9v5tsq_/sock"
                    }
                },
                "443-run-3.proj-2.gateway.test.conf": {
                    "type": "service",
                    "domain": "run-3.proj-2.gateway.test",
                    "https": true,
                    "project": "proj-2",
                    "service_id": "bcaa6ce30f2a4ffab279a44ef696ec7c",
                    "auth": true,
                    "client_max_body_size": 67108864,
                    "servers": {
                        "16fc0bd438d747bba810cef00bc137de": "unix:/tmp/tmpzyx08k1s/sock"
                    }
                }
            },
            "acme_settings": {
                "server": "https://acme.test/",
                "eab_kid": "test_eab_kid",
                "eab_hmac_key": "test_eab_hmac_key"
            }
        },
        "gateway_https": true
    },
    "openai": {
        "index": {
            "proj-2": {
                "chat": {
                    "model/2": {
                        "model": {
                            "type": "chat",
                            "name": "model/2",
                            "format": "tgi",
                            "chat_template": "test chat template",
                            "eos_token": "<|eot_id|>"
                        },
                        "domain": "run-3.proj-2.gateway.test",
                        "created": 1734905496
                    }
                }
            },
            "proj-1": {
                "chat": {
                    "model/1": {
                        "model": {
                            "type": "chat",
                            "name": "model/1",
                            "format": "openai",
                            "prefix": "/v1"
                        },
                        "domain": "run-1.proj-1.gateway.test",
                        "created": 1734902765
                    }
                }
            }
        },
        "services_index": {
            "40023ad58d624702b58fbda38489239e": [
                "proj-1",
                "chat",
                "model/1"
            ],
            "bcaa6ce30f2a4ffab279a44ef696ec7c": [
                "proj-2",
                "chat",
                "model/2"
            ]
        }
    },
    "stats_collector": {
        "path": "/var/log/nginx/dstack.access.log",
        "resolution": 1,
        "ttl": 300,
        "services": {
            "40023ad58d624702b58fbda38489239e": "run-1.proj-1.gateway.test",
            "c41cac40726b403692ca63292b4a3af8": "run-2.proj-2.gateway.test",
            "bcaa6ce30f2a4ffab279a44ef696ec7c": "run-3.proj-2.gateway.test"
        }
    }
}
"""


@pytest.mark.asyncio
async def test_migrate_from_state_v1(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    v1_file = tmp_path / "state.json"
    v2_file = tmp_path / "state-v2.json"
    v1_file.write_text(SAMPLE_STATE_V1)
    keys_dir.mkdir()
    (keys_dir / "proj-1").write_text("test key 1")
    (keys_dir / "proj-2").write_text("test key 2")

    migrate_from_state_v1(v1_file, v2_file, keys_dir)

    repo = GatewayProxyRepo.load(v2_file)
    assert await repo.get_config() == GlobalProxyConfig(
        acme_settings=ACMESettings(
            server="https://acme.test/",
            eab_kid="test_eab_kid",
            eab_hmac_key="test_eab_hmac_key",
        )
    )
    assert await repo.get_project("proj-1") == Project(name="proj-1", ssh_private_key="test key 1")
    assert await repo.get_project("proj-2") == Project(name="proj-2", ssh_private_key="test key 2")
    assert set(await repo.list_entrypoints()) == {
        ModelEntrypoint(project_name="proj-1", domain="gateway.proj-1.gateway.test", https=True),
        ModelEntrypoint(project_name="proj-2", domain="gateway.proj-2.gateway.test", https=True),
    }
    assert set(await repo.list_services()) == {
        Service(
            project_name="proj-1",
            run_name="run-1",
            domain="run-1.proj-1.gateway.test",
            https=True,
            auth=True,
            client_max_body_size=67108864,
            replicas=(
                Replica(
                    id="b894c006be5d4034bd751e57af0b4561",
                    app_port=11434,
                    ssh_destination="root@10.0.0.1",
                    ssh_port=11165,
                    ssh_proxy=None,
                ),
            ),
        ),
        Service(
            project_name="proj-2",
            run_name="run-2",
            domain="run-2.proj-2.gateway.test",
            https=True,
            auth=False,
            client_max_body_size=67108864,
            replicas=(
                Replica(
                    id="4aa53ef5759d400ea41e0ec6a34354ed",
                    app_port=8000,
                    ssh_destination="root@localhost",
                    ssh_port=10022,
                    ssh_proxy=SSHConnectionParams(
                        hostname="10.0.0.2",
                        username="root",
                        port=22,
                    ),
                ),
                Replica(
                    id="f1e60fedfc5a46f791f26a042b57b9f4",
                    app_port=8000,
                    ssh_destination="root@localhost",
                    ssh_port=10022,
                    ssh_proxy=SSHConnectionParams(
                        hostname="10.0.0.3",
                        username="root",
                        port=22,
                    ),
                ),
            ),
        ),
        Service(
            project_name="proj-2",
            run_name="run-3",
            domain="run-3.proj-2.gateway.test",
            https=True,
            auth=True,
            client_max_body_size=67108864,
            replicas=(
                Replica(
                    id="16fc0bd438d747bba810cef00bc137de",
                    app_port=80,
                    ssh_destination="root@localhost",
                    ssh_port=10022,
                    ssh_proxy=SSHConnectionParams(
                        hostname="10.0.0.4",
                        username="root",
                        port=22,
                    ),
                ),
            ),
        ),
    }
    assert await repo.list_models("proj-1") == [
        ChatModel(
            project_name="proj-1",
            name="model/1",
            created_at=datetime.fromtimestamp(1734902765),
            run_name="run-1",
            format_spec=OpenAIChatModelFormat(prefix="/v1"),
        )
    ]
    assert await repo.list_models("proj-2") == [
        ChatModel(
            project_name="proj-2",
            name="model/2",
            created_at=datetime.fromtimestamp(1734905496),
            run_name="run-3",
            format_spec=TGIChatModelFormat(
                chat_template="test chat template",
                eos_token="<|eot_id|>",
            ),
        )
    ]


EMPTY_STATE_V1 = """
{
    "store": {
        "services": {},
        "projects": {},
        "entrypoints": {},
        "nginx": {
            "configs": {},
            "acme_settings": {
                "server": null,
                "eab_kid": null,
                "eab_hmac_key": null
            }
        },
        "gateway_https": true
    },
    "openai": {
        "index": {},
        "services_index": {}
    },
    "stats_collector": {
        "path": "/var/log/nginx/dstack.access.log",
        "resolution": 1,
        "ttl": 300,
        "services": {}
    }
}
"""


@pytest.mark.asyncio
async def test_migrate_from_empty_state_v1(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    v1_file = tmp_path / "state.json"
    v2_file = tmp_path / "state-v2.json"
    v1_file.write_text(EMPTY_STATE_V1)

    migrate_from_state_v1(v1_file, v2_file, keys_dir)

    repo = GatewayProxyRepo.load(v2_file)
    assert await repo.get_config() == GlobalProxyConfig(
        acme_settings=ACMESettings(
            server=None,
            eab_kid=None,
            eab_hmac_key=None,
        )
    )
    assert await repo.list_entrypoints() == []
    assert await repo.list_services() == []


def test_not_migrates_if_no_state_v1(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    v1_file = tmp_path / "state.json"
    v2_file = tmp_path / "state-v2.json"
    migrate_from_state_v1(v1_file, v2_file, keys_dir)
    assert not v2_file.exists()


@pytest.mark.asyncio
async def test_not_migrates_if_migrated_before(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    v1_file = tmp_path / "state.json"
    v2_file = tmp_path / "state-v2.json"
    v1_file.write_text(EMPTY_STATE_V1)

    migrate_from_state_v1(v1_file, v2_file, keys_dir)
    state_v2_after_initial_migration = v2_file.read_text()

    repo = GatewayProxyRepo.load(v2_file)
    await repo.set_project(make_project("test-proj"))
    state_v2_after_write_operation = v2_file.read_text()
    assert state_v2_after_write_operation != state_v2_after_initial_migration

    migrate_from_state_v1(v1_file, v2_file, keys_dir)
    assert v2_file.read_text() == state_v2_after_write_operation
