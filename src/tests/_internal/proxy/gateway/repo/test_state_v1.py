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
)

SAMPLE_STATE_V1 = """
{
  "store": {
    "services": {
      "96588cfea40d4cb988e73b9d4e950653": {
        "id": "96588cfea40d4cb988e73b9d4e950653",
        "domain": "test-run-1.gtw.test",
        "https": true,
        "auth": true,
        "client_max_body_size": 134217728,
        "options": {
          "openai": {
            "model": {
              "type": "chat",
              "name": "llama3.1",
              "format": "openai",
              "prefix": "/v1"
            }
          }
        },
        "replicas": [
          {
            "id": "14d3c93205824020add766a766679028",
            "app_port": 11434,
            "ssh_host": "root@localhost",
            "ssh_port": 10022,
            "ssh_jump_host": "ubuntu@10.10.10.10",
            "ssh_jump_port": 22,
            "ssh_tunnel": {
              "temp_dir": "/tmp/tmpym471df7",
              "start_cmd": [],
              "exit_cmd": [],
              "check_cmd": []
            }
          }
        ]
      }
    },
    "projects": {
      "proj-1": [
        "96588cfea40d4cb988e73b9d4e950653"
      ]
    },
    "entrypoints": {
      "gateway.gtw.test": [
        "proj-1",
        "openai"
      ]
    },
    "nginx": {
      "configs": {
        "443-gateway.gtw.test.conf": {
          "type": "entrypoint",
          "domain": "gateway.gtw.test",
          "https": true,
          "proxy_path": "/api/openai/proj-1"
        },
        "443-test-run-1.gtw.test.conf": {
          "type": "service",
          "domain": "test-run-1.gtw.test",
          "https": true,
          "project": "proj-1",
          "service_id": "96588cfea40d4cb988e73b9d4e950653",
          "auth": true,
          "client_max_body_size": 134217728,
          "servers": {
            "14d3c93205824020add766a766679028": "unix:/tmp/tmpym471df7/sock"
          }
        }
      },
      "acme_settings": {
        "server": "https://acme.test/",
        "eab_kid": "test-eab-kid",
        "eab_hmac_key": "test-eab-hmac-key"
      }
    },
    "gateway_https": true
  },
  "openai": {
    "index": {
      "proj-1": {
        "chat": {
          "llama3.1": {
            "model": {
              "type": "chat",
              "name": "llama3.1",
              "format": "openai",
              "prefix": "/v1"
            },
            "domain": "test-run-1.gtw.test",
            "created": 1734471507
          }
        }
      }
    },
    "services_index": {
      "96588cfea40d4cb988e73b9d4e950653": [
        "proj-1",
        "chat",
        "llama3.1"
      ]
    }
  },
  "stats_collector": {
    "path": "/var/log/nginx/dstack.access.log",
    "resolution": 1,
    "ttl": 300,
    "services": {
      "96588cfea40d4cb988e73b9d4e950653": "test-run-1.gtw.test"
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
    (keys_dir / "proj-1").write_text("test key")

    migrate_from_state_v1(v1_file, v2_file, keys_dir)

    repo = GatewayProxyRepo.load(v2_file)
    assert await repo.get_config() == GlobalProxyConfig(
        acme_settings=ACMESettings(
            server="https://acme.test/",
            eab_kid="test-eab-kid",
            eab_hmac_key="test-eab-hmac-key",
        )
    )
    assert await repo.get_project("proj-1") == Project(name="proj-1", ssh_private_key="test key")
    assert await repo.list_entrypoints() == [
        ModelEntrypoint(project_name="proj-1", domain="gateway.gtw.test", https=True)
    ]
    assert await repo.list_services() == [
        Service(
            project_name="proj-1",
            run_name="test-run-1",
            domain="test-run-1.gtw.test",
            https=True,
            auth=True,
            client_max_body_size=134217728,
            replicas=[
                Replica(
                    id="14d3c93205824020add766a766679028",
                    app_port=11434,
                    ssh_destination="root@localhost",
                    ssh_port=10022,
                    ssh_proxy=SSHConnectionParams(
                        hostname="10.10.10.10", username="ubuntu", port=22
                    ),
                )
            ],
        )
    ]
    assert await repo.list_models("proj-1") == [
        ChatModel(
            project_name="proj-1",
            name="llama3.1",
            created_at=datetime.fromtimestamp(1734471507),
            run_name="test-run-1",
            format_spec=OpenAIChatModelFormat(prefix="/v1"),
        )
    ]
