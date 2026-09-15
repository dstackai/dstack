# Database

This document describes the `dstack` server rules of working with the database. Separately covered:

* DB migrations in `MIGRATIONS.md`
* Resource locking in `LOCKING.md`
* Pipeline-based background processing in `PIPELINES.md`.

## Connections

DB connections are a scarce resource. For example, a minimal RDS Postgres instance comes with ~80 connections. Increasing the number of connections requires
scaling the DB instance and is expensive. This section describes how the `dstack` server should use DB connections to avoid running out of them.

### Connection budget

The server creates one SQLAlchemy async engine per process with an `AsyncAdaptedQueuePool` of `DSTACK_DB_POOL_SIZE` (default 20) persistent connections plus `DSTACK_DB_MAX_OVERFLOW` (default 20) overflow connections, i.e. up to 40 connections per server process. When all of them are checked out, the next checkout waits `pool_timeout` (30 seconds) and then fails with:

```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 20 reached, connection timed out, timeout 30.00
```

Far more coroutines compete for the slots than there are slots. This works because each of them holds a connection for a short time.

A session does not hold a connection until it executes its first statement. From that moment until the session commits, rolls back, or closes, the connection is checked out and unavailable to anyone else. The invariant that follows:

**Hold a connection only while doing DB work. Do not keep a session open across when doing heavy work.**

On SQLite the same rule applies for a different reason: a long write transaction blocks every other writer for up to `busy_timeout` (30 seconds).

### Awaits that must not run inside a session

Anything whose completion depends on something other than the database:

* SSH: opening tunnels, `aexec()`, `acheck()`, any subprocess.
* HTTP to runners, shims, gateways, or external services.
* Cloud SDK calls, including those wrapped in `run_async()`. The thread pool executor is shared, so a saturated executor makes even a fast call wait.
* Retry loops with sleeps, and waiting on asyncio locks or events that other tasks control.
* Streaming a response to a client.

Fetch what you need before opening the session, or commit and close the session before the call and open a new one to apply the results:

```python
async with get_session_ctx() as session:
    # Load and lock what processing needs.
    context = await _load_context(session, item)

# No connection is held here.
result = await _do_network_work(context)

async with get_session_ctx() as session:
    # Apply results with a guarded update.
    await _apply_result(session, item, result)
```

### Session lifetime by context

**Pipelines**

Pipeline workers follow load, process, apply with a short session for the load and apply phases and no session during processing. See `PIPELINES.md`.

**API handlers**

The request session is created before the handler runs. The authentication dependency executes a SELECT on it, so a connection is checked out before the handler starts and stays checked out until the handler returns and the session commits.

This is acceptable because API handlers are assumed to be quick: read or write a few rows and return. A handler that needs to do slow work must not do it while holding the request session's connection. Either:

* Commit the session before the slow work. Committing returns the connection to the pool. The next statement on the session checks out a new connection and starts a new transaction, so any locks taken earlier are released, and the handler must not rely on them across the gap.
* Make the API async and move the slow work out of the handler.

The rule is not applied currently applied to API handlers strictly: a handler may make one or a few network calls while holding the connection.

**Startup**

Migrations and server initialization may hold a connection and a session-level advisory lock for long: they run once per process, before anything else competes for connections. Recurring cross-replica coordination should use the pipeline lock columns instead.

### Lock waits

A coroutine blocked on a DB-level lock holds its connection while it waits. This applies to `SELECT ... FOR UPDATE` and to `pg_advisory_lock` alike: the waiter occupies a pool slot on its replica until the holder releases the lock. A lock held for a long time thus costs one slot on the holder plus one per waiter, and a hung holder pins all of them.

Keep locked regions short and bounded. See `LOCKING.md` for how to take advisory locks correctly.

### Settings

`DSTACK_DB_COMMAND_TIMEOUT` (default 300 seconds) bounds every operation on a Postgres connection, so a coroutine waiting on a connection whose socket died silently gets an error and releases the slot instead of holding it forever. It applies to migrations too, since they run on the same engine, so it must leave room for index builds and backfills.

`DSTACK_DB_POOL_SIZE` and `DSTACK_DB_MAX_OVERFLOW` size the pool per process. Raising them lets more coroutines hold connections at once, which hides a long hold rather than fixing it, and each replica needs `pool_size + max_overflow` connections from the Postgres `max_connections` budget.
