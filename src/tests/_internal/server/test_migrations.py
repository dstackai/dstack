from pathlib import Path

import pytest
from alembic.command import check, upgrade
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy import create_engine


def test_no_database_migration_needs_to_be_added(monkeypatch: pytest.MonkeyPatch):
    server_dir = Path(__file__).parent.joinpath("../../../dstack/_internal/server").resolve()
    monkeypatch.chdir(server_dir)

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.attributes["connection"] = create_engine("sqlite://").connect()

    try:
        upgrade(alembic_cfg, "head")
        check(alembic_cfg)
    except CommandError as e:
        pytest.fail(str(e))
