# Locking

The `dstack` server supports SQLite and Postgres databases with two implementations of resource locking to handle concurrent access:

* In-memory locking for SQLite.
* DB-level locking for Postgres.

## SQLite locking

SQLite is missing efficient mechanisms to handle concurrent writes (e.g. select for update), so `dstack` implements in-memory resource-level locking. In-memory locking works correctly under the assumption that there is only one server instance (process), which is a `dstack` limitation when using SQLite.

The in-memory locking is implemented via locksets. Locksets are Python sets that store IDs of locked resources. Concurrent access to locksets is guarded with asyncio locks:

```python
lock, lockset = get_lockset("my_table")
async with lock:
    # select resource that is not in lockset
    lockset.add(resource.id)
try:
    process_resource(resource)
finally:
    lockset.remove(resource.id)
```

Locksets are an optimization. One can think of them as per-resource-id locks that allow independent locking of different resources.

## Postgres locking

Postgres resource locking is implemented via standard SELECT FOR UPDATE.
SQLAlchemy provides `.with_for_update()` that has no effect if SELECT FOR UPDATE is not supported as in SQLite.

There are few places that rely on advisory locks as when generating unique resource names or serializing server initialization across replicas. See **Advisory locks** below.

## Working with locks

Concurrency is hard. Concurrency with locking is especially hard. Below you'll find common patterns and gotchas when working with locks to make it a bit more manageable.

**A task should acquire locks on resources it modifies**

This is common sense. An alternative could be the inverse: job processing cannot run in parallel with run processing, so job processing takes run lock. This indirection complicates things and is discouraged. In this example, run processing should take job lock instead.

**Start new transaction after acquiring a lock to see other transactions changes in SQLite.**

```python
select resource ids by names
lock resource ids
await session.commit()
# The next statement will start new transaction
select ...
```

> SQLite exhibits Snapshot Isolation. When a read transaction starts, that reader continues to see an unchanging "snapshot" of the database file as it existed at the moment in time when the read transaction started. Any write transactions that commit while the read transaction is active are still invisible to the read transaction, because the reader is seeing a snapshot of database file from a prior moment in time. Source: https://www.sqlite.org/isolation.html

Thus, if a new transaction is not started, you won't see changes that concurrent transactions made before you acquired the lock.

This is not relevant for Postgres since it doesn't rely on in-memory locking (and it also runs on Read Committed isolation level by default). 

**Release in-memory locks only after committing changes**

```python
# Don't do this!
lock resources
unlock resources
do smth else
await session.commit()
```

```python
# Do this!
lock resources
await session.commit()
unlock resources
```

If a transaction releases a lock before committing changes, the changes may not be visible to another transaction that acquired the lock and relies upon seeing all committed changes.

**Using `joinedload` when selecting `.with_for_update()`**

Using `joinedload` and `.with_for_update()` triggers an error in case of no related rows because `joinedload` produces OUTER LEFT JOIN and SELECT FOR UPDATE cannot be applied to the nullable side of an OUTER JOIN. Here's the options:

* Use `.with_for_update(of=MainModel)`.
* Select with `selectinload`
* First select with  `.with_for_update()` without loading related attributes and then re-select with `joinedload` without `.with_for_update()`.
* Use regular `.join()` to lock related resources, but you may get 0 rows if there is no related row to join.

**Always use `.with_for_update(key_share=True)` unless you plan to delete rows or update a primary key column**

If you `SELECT FOR UPDATE` from a table that is referenced in a child table via a foreign key, it can lead to deadlocks if the child table is updated because Postgres will issue a `FOR KEY SHARE` lock on the parent table rows to ensure valid foreign keys. For this reason, you should always do `SELECT FOR NO KEY UPDATE` (.`with_for_update(key_share=True)`) if primary key columns are not modified. `SELECT FOR NO KEY UPDATE` is not blocked by a `FOR KEY SHARE` lock, so no deadlock.

**Lock unique names**

The following pattern can be used to lock a unique name of some resource type:

```python
lock_namespace = f"fleet_names_{project.name}"
if get_db().dialect_name == "sqlite":
    # Start new transaction to see committed changes after lock
    await session.commit()
elif get_db().dialect_name == "postgresql":
    await session.execute(
        select(func.pg_advisory_xact_lock(string_to_lock_id(lock_namespace)))
    )

lock, _ = get_locker(get_db().dialect_name).get_lockset(lock_namespace)
async with lock:
    # ... select taken names, use a unique name
    await session.commit()
```

Note that:

* This pattern works assuming that Postgres is using default isolation level Read Committed. By the time a transaction acquires the advisory lock, all other transactions that can take the name have committed, so their changes can be seen and a unique name is taken.
* SQLite needs a commit before selecting taken names due to Snapshot Isolation as noted above.

**Advisory locks**

Postgres has two kinds of advisory locks:

* `pg_advisory_xact_lock` is released when the transaction ends. The unique names pattern above uses it.
* `pg_advisory_lock` is bound to the connection. It survives commit and rollback and is released only by `pg_advisory_unlock` on the same connection or when the connection closes. `advisory_lock_ctx()` in `services/locking.py` wraps this kind for work that must span several transactions, such as migrations or server initialization.

Either use `pg_advisory_xact_lock` within a single transaction, or use `advisory_lock_ctx()` and follow these rules:

* Bind it to an `AsyncConnection` from `engine.connect()`, not to an `AsyncSession`. If the session commits inside the block, its next statement may run on a different pooled connection, and `pg_advisory_unlock` goes to a connection that never held the lock. Postgres only returns `false` with a warning in this case, so the failure is silent: the lock stays on an idle pooled connection until the process exits, and every replica blocks forever on its next acquire. See https://github.com/dstackai/dstack/issues/3881 for an example.
* Keep the locked block short and bounded. Every waiter is blocked inside `pg_advisory_lock` holding a DB connection of its own, so a long or hung holder pins one connection per waiter. See `DATABASE.md`.

```python
async with get_db().engine.connect() as connection:
    async with advisory_lock_ctx(
        bind=connection,
        dialect_name=get_db().dialect_name,
        resource="server_init",
    ):
        async with get_session_ctx() as session:
            # The session may commit freely: the lock lives on `connection`.
            ...
```

A released connection goes back to the pool, so a lock that failed to release stays there too. `_release_advisory_lock()` tolerates failures because the common one is an invalidated connection, in which case Postgres has already dropped the lock. A release that fails on a live connection strands the lock.

**Use `AsyncExitStack`**

In-memory locking typically requires taking lock for long (until commit).
Using lock context managers for in-memory locking is often hard because the lock is tied to a block:

```python
if something:
    # Can't do this because the lock will be released before commit. How to lock?
    async with get_locker(get_db().dialect_name).lock_ctx(...):
        # ...
# ...
await session.commit()
```

Use [`contextlib.AsyncExitStack`](https://docs.python.org/3/library/contextlib.html#contextlib.AsyncExitStack):

```python
async with AsyncExitStack() as exit_stack:
    if something:
        # The lock will be released only on stack exit, so it's ok.
        await exit_stack.enter_async_context(
            get_locker(get_db().dialect_name).lock_ctx(...)
        )
        # ...
    # ...
    await session.commit()
```
