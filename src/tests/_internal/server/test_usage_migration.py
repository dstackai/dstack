"""Initial DS-002 migration creates the final schema without rewriting existing data."""

import importlib
import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy_utils import UUIDType

MIGRATION = (
    "dstack._internal.server.migrations.versions.2026."
    "11_16_1201_9a2e8f1f3c37_add_gateway_usage_batches"
)


def run_case(conn, populated):
    # Independent pre-existing data makes an accidental rewrite/drop observable.
    meta = sa.MetaData()
    gateways = sa.Table(
        "gateways",
        meta,
        sa.Column("id", UUIDType(binary=False), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
    )
    replicas = sa.Table(
        "gateway_computes",
        meta,
        sa.Column("id", UUIDType(binary=False), primary_key=True),
        sa.Column("gateway_id", UUIDType(binary=False)),
    )
    meta.create_all(conn)
    parent, replica = uuid.uuid4(), uuid.uuid4()
    conn.execute(gateways.insert().values(id=parent, name="existing-gateway"))
    conn.execute(replicas.insert().values(id=replica, gateway_id=parent))
    before = conn.execute(sa.select(gateways)).all(), conn.execute(sa.select(replicas)).all()
    migration = importlib.import_module(MIGRATION)
    with Operations.context(MigrationContext.configure(conn)):
        migration.upgrade()
        assert (
            conn.execute(sa.select(gateways)).all(),
            conn.execute(sa.select(replicas)).all(),
        ) == before
        inspector = sa.inspect(conn)
        assert "usage_collectors" not in inspector.get_table_names()
        tables = sa.MetaData()
        batches = sa.Table("usage_batches", tables, autoload_with=conn)
        counters = sa.Table("usage_counters", tables, autoload_with=conn)
        assert {"gateway_id", "gateway_replica_id"} <= set(batches.c.keys())
        assert "collector_id" not in batches.c
        assert "usage_baches_id" in counters.c and "receipt_id" not in counters.c
        assert inspector.get_foreign_keys("usage_batches") == []
        assert {
            tuple(c["column_names"]) for c in inspector.get_unique_constraints("usage_batches")
        } == {
            ("gateway_replica_id", "batch_id"),
            ("gateway_replica_id", "interval_start"),
        }
        assert inspector.get_pk_constraint("usage_counters")["constrained_columns"] == [
            "usage_baches_id",
            "consumer_subject_id",
            "service_id",
        ]
        fk = inspector.get_foreign_keys("usage_counters")
        assert len(fk) == 1
        assert fk[0]["constrained_columns"] == ["usage_baches_id"]
        assert fk[0]["referred_table"] == "usage_batches" and fk[0]["referred_columns"] == ["id"]
        if not populated:
            migration.downgrade()
            assert set(inspector.get_table_names()) >= {"gateways", "gateway_computes"}
            assert "usage_batches" not in sa.inspect(conn).get_table_names()
            assert (
                conn.execute(sa.select(gateways)).all(),
                conn.execute(sa.select(replicas)).all(),
            ) == before
            return
        batch_id = uuid.uuid4().hex
        conn.execute(
            batches.insert().values(
                id=batch_id,
                gateway_replica_id=replica.hex,
                gateway_id=parent.hex,
                batch_id="b1",
                interval_start=datetime(2026, 11, 17, 10),
                interval_end=datetime(2026, 11, 17, 10, 1),
                received_at=datetime(2026, 11, 17, 10, 2),
                content='{"fixture":true}',
            )
        )
        conn.execute(
            counters.insert().values(
                usage_baches_id=batch_id,
                consumer_subject_id="u",
                service_id="s",
                prompt_tokens=20,
                cached_prompt_tokens=5,
                completion_tokens=3,
                total_tokens=23,
                unknown_usage_attempts=0,
            )
        )
        rows = conn.execute(sa.select(batches)).all()
        conn.execute(replicas.delete())
        conn.execute(gateways.delete())
        assert conn.execute(sa.select(batches)).all() == rows
        assert conn.scalar(sa.select(sa.func.sum(counters.c.total_tokens))) == 23
        assert (
            conn.scalar(
                sa.select(sa.func.count()).select_from(
                    counters.join(batches, counters.c.usage_baches_id == batches.c.id)
                )
            )
            == 1
        )
        with pytest.raises(ValueError, match="backup"):
            migration.downgrade()
        assert conn.execute(sa.select(batches)).all() == rows
        assert conn.scalar(sa.select(sa.func.count()).select_from(counters)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dialect", ["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)]
)
@pytest.mark.parametrize("populated", [False, True])
async def test_initial_usage_schema_preserves_existing_data(tmp_path, request, dialect, populated):
    url = (
        f"sqlite+aiosqlite:///{tmp_path / 'migration.sqlite'}"
        if dialect == "sqlite"
        else request.getfixturevalue("postgres_container")
    )
    engine = create_async_engine(url)
    schema = "usage_test_" + uuid.uuid4().hex
    try:
        async with engine.begin() as conn:
            if dialect == "postgres":
                await conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
                await conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            await conn.run_sync(lambda c: run_case(c, populated))
            if dialect == "postgres":
                await conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
    finally:
        await engine.dispose()
