# Locking

The `dstack` server supports SQLite and Postgres databases
with two implementations of resource locking to handle concurrent access:

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

There are few places that rely on advisory locks as when generating unique resource names.

## Working with locks

Concurrency is hard. Below you'll find common patterns and gotchas when working with locks to make it a bit more manageable.

**A task should acquire locks on resources it modifies**

This is a common sense approach. An alternative could be the inverse: job processing cannot run in parallel with run processing, so job processing takes run lock. This indirection complicates things and is discouraged. In this example, run processing should take job lock instead.


**Start new transaction after acquiring a lock to see other transactions changes in SQLite.**

```python
select resource ids by names
lock resource ids
await session.commit()
# The next statement will start new transaction
select ...
```

> SQLite exhibits "snapshot isolation". When a read transaction starts, that reader continues to see an unchanging "snapshot" of the database file as it existed at the moment in time when the read transaction started. Any write transactions that commit while the read transaction is active are still invisible to the read transaction, because the reader is seeing a snapshot of database file from a prior moment in time. Source: https://www.sqlite.org/isolation.html

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

**Don't use joinedload when selecting .with_for_update()**

In fact, using `joinedload` and `.with_for_update()` will trigger an error because `joinedload` produces OUTER LEFT JOIN that cannot be used with SELECT FOR UPDATE. A regular `.join()` can be used to lock related resources but it may lead to no rows if there is no row to join. Usually, you'd select with `selectinload` or first select with  `.with_for_update()` without loading related attributes and then re-selecting with `joinedload` without `.with_for_update()`.
