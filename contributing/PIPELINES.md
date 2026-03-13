# Pipelines

This document describes how the `dstack` server implements background processing via so-called "pipelines".

*Historical context: `dstack` used to do all background processing via scheduled tasks. A scheduled task would process a specific resource type like volumes or runs by keeping DB transaction open for the entire processing duration and keeping the resource lock with SELECT FOR UPDATE (or in-memory lock on SQLite). This approach didn't scale well because the number of DB connections was a huge bottleneck. Pipelines replaced scheduled tasks: the do all the heavy processing outside of DB transactions and write locks to DB columns.*

## Overview

* Resources are continuously processed in the background by pipelines. A pipeline consists of a fetcher, workers, and a heartbeater.
* A fetcher selects rows to be processed from the DB, marks them as locked in the DB, and puts them into an in-memory queue. 
* Workers consume rows from the in-memory queue, process the rows, and unlock them.
* The locking (unlocking) is done by setting (unsetting) `lock_expires_at`, `lock_token`, `lock_owner`.
* If the replica/pipeline dies, the rows stay locked in the db. Another replica picks up the rows after `lock_expires_at`.
* `lock_token` prevents stale replica/pipeline to update the rows already picked up by the new replica.
* `lock_owner` stores the pipeline that's locked the row so that only that pipeline can recover if it's stale.
* A heartbeater tracks all rows in the pipeline (in the queue or in processing), and updates the lock expiration. This allows setting small `lock_expires_at` and picking up stale rows quickly
* A fetcher performs the fetch when the queue size goes under a configured lower limit. It has exponential retry delays between empty fetches, thus reducing load on the DB.
* There is a fetch hint mechanism that services can use to notify the pipelines within the replica – in that case the fetcher stops sleeping and fetches immediately.
* Each pipeline locks one main resource but may lock related resources as well. It's not necessary to heartbeat related resources if the pipeline ensures no one else can re-lock them. This is typically done via setting and respecting `lock_owner`.

Related notes:

* All write APIs must respect DB-level locks. The endpoints can either try to acquire the lock with a timeout and error or provide an async API by storing the request in the DB.

## Implementation checklist

Brief checklist for implementing a new pipeline:

1. Fetcher locks only rows that are ready for processing:
`status/time` filters, `lock_expires_at` is empty or expired, and `lock_owner` is empty or equal to the pipeline name. Keep the fetch order stable with `last_processed_at`.
2. Fetcher takes row locks with `skip_locked` and updates `lock_expires_at`, `lock_token`, `lock_owner` before enqueueing items.
3. Worker keeps heavy work outside DB sessions. DB sessions should be short and used only for refetch/locking and final apply.
4. Apply stage updates rows using update maps/update rows, not by relying on mutating detached ORM models.
5. Main apply update is guarded by `id + lock_token`. If the update affects `0` rows, the item is stale and processing results must not be applied.
6. Successful apply updates `last_processed_at` and unlocks resources that were locked by this item.
7. If related lock is unavailable, reset main lock for retry: keep `lock_owner`, clear `lock_token` and `lock_expires_at`, and set `last_processed_at` to now.
8. Register the pipeline in `PipelineManager` and hint fetch from services after commit via `pipeline_hinter.hint_fetch(Model.__name__)`.
9. Add minimum tests: fetch eligibility/order, successful unlock path, stale lock token path, and related lock contention retry path.

## Typical worker structure

Most workers are easiest to reason about when `process()` is split into three phases:

1. Load/refetch: open a short DB session, refetch the locked main row by `id + lock_token`, lock any required related rows, and gather any extra data needed for processing.
2. Process: do the heavy work outside DB sessions and build result objects or update maps instead of mutating detached ORM models.
3. Apply: open a short DB session, guard the main update by `id + lock_token`, resolve time placeholders, apply related updates, emit events, and unlock rows.

A dedicated context object is often useful for the load step when the worker needs multiple loaded models, related lock metadata, or derived values that should be passed cleanly into processing and apply. For very small pipelines, a direct load -> process -> apply flow may still be clearer.

Workers can share one context type and one apply function across all states even if the processing logic differs by state:

```python
async def process(item):
    context = await _load_process_context(item)
    if context is None:
        return
    result = await _process_item(context)
    await _apply_process_result(item, context, result)
```

Sometimes state-specific helpers are still the cleanest option, but they can still share a common apply phase if all states write results in the same general shape:

```python
async def process(item):
    if item.status == Status.PENDING:
        context = await _load_pending_context(item)
    elif item.status == Status.RUNNING:
        context = await _load_running_context(item)
    else:
        return
    if context is None:
        return
    result = await _process_item(context)
    await _apply_process_result(item, context, result)
```

If different states have materially different write-side behavior, different apply paths are fine as well. This commonly happens when one state does a normal guarded update while another does delete-or-cleanup work with different related updates:

```python
async def process(item):
    if item.to_be_deleted:
        await _process_to_be_deleted_item(item)
    elif item.status == Status.SUBMITTED:
        await _process_submitted_item(item)
```

It's ok not to force all pipelines into one exact shape.

## Implementation patterns

**Guarded apply by lock token**

When writing processing results, update the main row with a filter by both `id` and `lock_token`. This guarantees that only the worker that still owns the lock can apply its results. If the update affects no rows, treat the item as stale and skip applying other changes (status changes, related updates, events). A stale item means another worker or replica already continued processing.

**Locking many related resources**

A pipeline may need to lock a potentially big set of related resource, e.g. fleet pipeline locking all fleet's instances. For this, do one SELECT FOR UPDATE of non-locked instances and one SELECT to see how many instances there are, and check if you managed to lock all of them. If fail to lock, release the main lock and try processing on another fetch iteration. You may keep `lock_owner` on the main resource or set `lock_owner` on locked related resource and make other pipelines respect that to guarantee the eventual locking of all related resources and avoid lock starvation.

**Locking a shared related resource**

Multiple main resources may need to lock the same related resource, e.g. multiple jobs may need to change the shared instance. In this case it's not sufficient to set `lock_owner` on the related resource to the pipeline name because workers processing different main resources can still race with each other. To avoid heartbeating the related resource, you may include main resource id in `lock_owner`, e.g. set `lock_owner = f"{Pipeline.__name__}:{item.id}"`.

**Reset-and-retry when related lock is unavailable**

If a worker cannot lock a required related resource, it should release only the main lock state needed for fast retry: unset `lock_token` and `lock_expires_at`, keep `lock_owner`, and set `last_processed_at` to now. This avoids long waiting and lets the same pipeline retry quickly on the next fetch iteration while other pipelines can still respect ownership intent.

**Dealing with side effects**

If processing has side effects and the apply phase fails due to a lock mismatch, there are several options: a) revert side effects b) make processing idempotent, i.e. next processing iteration detects side effects does not perform duplicating actions c) log side effects as errors and warn user about possible issues such as orphaned instances – as a temporary solution.

**Bulk apply with one consistent current time**

When apply needs to update multiple rows (main + related resources), build update maps/update rows first and resolve current-time placeholders once in the apply transaction using `NOW_PLACEHOLDER` + `resolve_now_placeholders()`. This keeps timestamps consistent across all rows and avoids subtle ordering bugs when the same processing pass writes several `*_at` fields.

## Performance analysis

* Pipeline throughput = workers_num / worker_processing_time. So quick tasks easily give high-throughput pipelines, e.g. 1s task with 20 workers is 1200 tasks/min.
A slow 30s task gives only 40 tasks/min with the same number of workers. We can increase the number of workers but the peak memory usage will grow proportionally.
In general, workers should be optimized to be as quick as possible to improve throughput.
* Processing latency (wait) is close to 0 due to fetch hints if the pipeline is not saturated. In general, latency = queue_size / throughput.
* In-memory queue maxsize provides a cap on memory usage and recovery time after crashes (number of locked items to retry).
* Fetcher's DB load is proportional to the number of pipelines and is expected to be negligible. Workers can put a considerable read/write DB load as it's proportional to the number of workers. This can be optimized by batching workers' writes. Workers do processing outside of transactions so DB connections won't be a bottleneck.
* There is a risk of lock starvation if a worker needs to lock all related resources. This is to be mitigated by 1) related pipelines checking `lock_owner` and skip locking to let the parent pipeline acquire all the locks eventually and 2) do the related resource locking only on paths that require it.
