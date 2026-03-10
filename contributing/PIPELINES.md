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

## Implementation patterns

**Locking many related resources**

A pipeline may need to lock a potentially big set of related resource, e.g. fleet pipeline locking all fleet's instances. For this, do one SELECT FOR UPDATE of non-locked instances and one SELECT to see how many instances there are, and check if you managed to lock all of them. If fail to lock, release the main lock and try processing on another fetch iteration. You may keep `lock_owner` on the main resource or set `lock_owner` on locked related resource and make other pipelines respect that to guarantee the eventual locking of all related resources and avoid lock starvation.

**Locking a shared related resource**

Multiple main resources may need to lock the same related resource, e.g. multiple jobs may need to change the shared instance. In this case it's not sufficient to set `lock_owner` on the related resource to the pipeline name because workers processing different main resources can still race with each other. To avoid heartbeating the related resource, you may include main resource id in `lock_owner`, e.g. set `lock_owner = f"{Pipeline.__name__}:{item.id}"`.

## Performance analysis

* Pipeline throughput = workers_num / worker_processing_time. So quick tasks easily give high-throughput pipelines, e.g. 1s task with 20 workers is 1200 tasks/min.
A slow 30s task gives only 40 tasks/min with the same number of workers. We can increase the number of workers but the peak memory usage will grow proportionally.
In general, workers should be optimized to be as quick as possible to improve throughput.
* Processing latency (wait) is close to 0 due to fetch hints if the pipeline is not saturated. In general, latency = queue_size / throughput.
* In-memory queue maxsize provides a cap on memory usage and recovery time after crashes (number of locked items to retry).
* Fetcher's DB load is proportional to the number of pipelines and is expected to be negligible. Workers can put a considerable read/write DB load as it's proportional to the number of workers. This can be optimized by batching workers' writes. Workers do processing outside of transactions so DB connections won't be a bottleneck.
* There is a risk of lock starvation if a worker needs to lock all related resources. This is to be mitigated by 1) related pipelines checking `lock_owner` and skip locking to let the parent pipeline acquire all the locks eventually and 2) do the related resource locking only on paths that require it.
