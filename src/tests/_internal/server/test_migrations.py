import pytest
from alembic.command import check, upgrade, util
from alembic.config import Config
from sqlalchemy import create_engine


def test_a_database_migration_needs_to_be_added(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir("src/dstack/_internal/server")

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.attributes["connection"] = create_engine("sqlite://").connect()

    try:
        upgrade(alembic_cfg, "head")
        check(alembic_cfg)
    except util.CommandError as e:
        pytest.fail(str(e))
