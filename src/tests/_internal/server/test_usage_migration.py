"""Exercise the rewritten Gateway usage revision with isolated databases."""

import importlib
import uuid
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy_utils import UUIDType

from dstack._internal.server.db import Database

MIGRATION = (
    "dstack._internal.server.migrations.versions.2026."
    "11_16_1201_9a2e8f1f3c37_add_gateway_usage_batches"
)


def run_case(conn, populated):
    # Minimal tables from the parent revision, with data that the new revision must preserve.
    metadata = sa.MetaData()
    parents = [
        sa.Table(name, metadata, sa.Column("id", UUIDType(binary=False), primary_key=True))
        for name in ("users", "runs", "gateways", "gateway_computes")
    ]
    metadata.create_all(conn)
    user, run, gateway, replica = (uuid.uuid4() for _ in parents)
    for table, id_ in zip(parents, (user, run, gateway, replica)):
        conn.execute(table.insert().values(id=id_))
    migration = importlib.import_module(MIGRATION)
    assert (migration.revision, migration.down_revision) == ("9a2e8f1f3c37", "6b5610ff36c1")
    with Operations.context(MigrationContext.configure(conn)):
        migration.upgrade()
        inspector = sa.inspect(conn)
        assert set(inspector.get_table_names()) == {*metadata.tables, "usage_batches"}
        batches = sa.Table("usage_batches", sa.MetaData(), autoload_with=conn)
        identity = {"id", "user_id", "run_id", "gateway_id", "gateway_replica_id"}
        times = {"interval_start", "interval_end", "received_at"}
        counters = {
            "prompt_tokens",
            "cached_prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "unknown_usage_attempts",
        }
        assert set(batches.c.keys()) == identity | times | counters | {
            "batch_id",
            "batch_row_number",
        }
        assert all(not col.nullable for col in batches.c)
        for name in identity:
            coltype = batches.c[name].type
            if conn.dialect.name == "sqlite":
                assert isinstance(coltype, sa.CHAR) and coltype.length == 32
            else:
                assert isinstance(coltype, sa.UUID)
        assert all(
            isinstance(batches.c[name].type, sa.DateTime) and not batches.c[name].type.timezone
            for name in times
        )
        assert all(isinstance(batches.c[name].type, sa.BigInteger) for name in counters)
        assert batches.c.batch_row_number.type.compile(dialect=conn.dialect) == "INTEGER"
        assert batches.c.batch_id.type.length == 128
        assert inspector.get_pk_constraint("usage_batches")["constrained_columns"] == ["id"]
        (fk,) = inspector.get_foreign_keys("usage_batches")
        assert fk["constrained_columns"] == ["user_id"]
        assert fk["referred_table"] == "users" and fk["referred_columns"] == ["id"]
        assert fk["options"]["ondelete"] == "RESTRICT"
        (pair,) = inspector.get_unique_constraints("usage_batches")
        assert pair["column_names"] == ["gateway_replica_id", "batch_id", "user_id", "run_id"]
        indexes = {
            ix["name"]: ix
            for ix in inspector.get_indexes("usage_batches")
            if not ix.get("duplicates_constraint")
        }
        assert {name: ix["column_names"] for name, ix in indexes.items()} == {
            "uq_usage_batches_replica_batch": ["gateway_replica_id", "batch_id"],
            "uq_usage_batches_replica_minute": ["gateway_replica_id", "interval_start"],
            "ix_usage_batches_gateway_interval": ["gateway_id", "interval_start"],
            "ix_usage_batches_user_id": ["user_id"],
            "ix_usage_batches_run_id": ["run_id"],
        }
        for index in indexes.values():
            assert index["unique"] == index["name"].startswith("uq_")
            if index["unique"]:
                predicate = index["dialect_options"][f"{conn.dialect.name}_where"]
                assert str(predicate).strip("()") == "batch_row_number = 0"

        if not populated:
            migration.downgrade()
            assert set(sa.inspect(conn).get_table_names()) == set(metadata.tables)
            for table, id_ in zip(parents, (user, run, gateway, replica)):
                assert conn.scalar(sa.select(table.c.id)) == id_
            migration.upgrade()
            assert sa.inspect(conn).has_table("usage_batches")
            return

        def stored_id(value):
            return value.hex if conn.dialect.name == "sqlite" else value

        start = datetime(2026, 11, 20, 10)
        end = start + timedelta(minutes=1)
        common = dict(
            gateway_replica_id=stored_id(replica),
            gateway_id=stored_id(gateway),
            batch_id="B1",
            interval_start=start,
            interval_end=end,
            received_at=end + timedelta(seconds=4),
            user_id=stored_id(user),
        )

        def add_row(**changes):
            row = dict(
                **common,
                id=stored_id(uuid.uuid4()),
                run_id=stored_id(uuid.uuid4()),
                batch_row_number=1,
                prompt_tokens=15,
                cached_prompt_tokens=3,
                completion_tokens=5,
                total_tokens=20,
                unknown_usage_attempts=0,
            )
            conn.execute(batches.insert().values(row | changes))

        add_row(run_id=stored_id(run), batch_row_number=0)
        add_row(prompt_tokens=5, cached_prompt_tokens=0, completion_tokens=2, total_tokens=7)
        assert conn.execute(
            sa.select(batches.c.batch_row_number, batches.c.total_tokens).order_by(
                batches.c.batch_row_number
            )
        ).all() == [(0, 20), (1, 7)]
        assert conn.scalar(sa.select(sa.func.sum(batches.c.total_tokens))) == 27

        invalid = [
            dict(batch_row_number=-1),
            dict(batch_id="other-batch", batch_row_number=0),
            dict(interval_start=end, batch_row_number=0),
            dict(run_id=stored_id(run)),
            dict(cached_prompt_tokens=16),
            dict(total_tokens=21),
            dict(user_id=stored_id(uuid.uuid4())),
        ]
        if conn.dialect.name == "sqlite":
            invalid += [dict(batch_row_number=1.5), dict(unknown_usage_attempts=1.5)]
        for changes in invalid:
            with pytest.raises(sa.exc.IntegrityError), conn.begin_nested():
                add_row(**changes)

        for table in parents[1:]:
            conn.execute(table.delete())
        with pytest.raises(sa.exc.IntegrityError), conn.begin_nested():
            conn.execute(parents[0].delete())
        with pytest.raises(ValueError, match="backup"):
            migration.downgrade()
        assert conn.scalar(sa.select(sa.func.sum(batches.c.total_tokens))) == 27


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
    db = Database(url)
    schema = "usage_test_" + uuid.uuid4().hex
    try:
        async with db.engine.begin() as conn:
            if dialect == "postgres":
                await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            else:
                assert await conn.scalar(sa.text("PRAGMA foreign_keys")) == 1
            await conn.run_sync(lambda c: run_case(c, populated))
            if dialect == "postgres":
                await conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
    finally:
        await db.engine.dispose()
