# Orphan cleanup

`dstack` can leave cloud resources it no longer tracks: the server crashes or loses its lock between a provider call that creates resources and the commit that records them, the provider returns an error after creating them, or termination gives up after retrying. Orphan cleanup finds such resources by listing them in the provider and matching them with the DB, then reports or deletes them.

How a backend supports it is described in [BACKENDS.md](BACKENDS.md#32-orphan-cleanup-support). This doc covers the server side.

## `provider_ref`

Each record that provisions resources gets a `provider_ref` (12-char string). Backends set it on the resources they create (as a tag or in names) and report it back when listing.

- Only instances own `provider_ref`s (`InstanceModel.provider_ref`). Fleet instances get it on creation, for `create_instance()`. Placeholder instances, created for job submissions before `run_job()`, get it on creation too, pass it to `run_job()` (`JobSubmission.provider_ref`), and keep it when promoted.
- Every issued `provider_ref` is also recorded in `ProviderRefModel`, committed with its owner before any provider call. Records are not deleted with owners, so resources of a deleted owner are still recognized. This matters for placeholder instances, which are deleted when a `run_job()` fails, possibly after creating resources.
- Compute groups (`run_jobs()`) are not supported: their instances get no `provider_ref`, and backends must not set it on compute group resources.

## Cleanup unit and enrollment

An `OrphanCleanupModel` row exists per project backend (`BackendModel`) that supports resource listing. A scheduled task periodically creates rows in batches for backends of projects that have issued `provider_ref`s. Enrolling periodically instead of in a migration covers backends created by any replica, including older replicas during rolling deployments.

## `OrphanCleanupPipeline`

The pipeline processes each row at most once per cleanup interval (`DSTACK_SERVER_ORPHAN_CLEANUP_INTERVAL_SECONDS`). Failed cleanups are retried with an increasing delay.

Processing a row:

- STEP 1: Check whether the backend may have new orphans: it was never cleaned up, the cleanup mode changed, or the project had instance or job activity since the last clean cleanup (`clean_at`). If not, the row is only marked processed. Checking activity here rather than in the fetch query keeps fetching cheap regardless of project sizes, at the cost of a small query and row update per enrolled backend per interval.
- STEP 2: List the backend's resource groups (`list_resource_groups()`). A resource group is one provisioning attempt as found in the provider: the owner resource (`primary_id`, the instance) and internal resources created with it.
- STEP 3: Load the project's `ProviderRefModel` records and their instances (including soft-deleted ones) by `provider_ref`, in one statement. An instance is committed with its record, so it can't be missed while the record is seen.
- STEP 4: Classify each group:
    - Instance found:
        - `PENDING`, `TERMINATING`: skip, since the resources may be in flight. An error is logged if a pending instance's resources look stuck.
        - `TERMINATED`: orphan.
        - `PROVISIONING`, `IDLE`, `BUSY`: tracked if the base backend and `primary_id` match the instance's provisioning data, orphan otherwise.
        - Without provisioning data: ignored with an error log.
    - Record found without an instance: orphan. The owner was deleted, e.g. a placeholder instance after a failed `run_job()`, so nothing can be creating its resources anymore.
    - No record: ignored. Resources of other servers and projects are never touched.
- STEP 5: Owners that were provisioned or terminated around the listing are skipped instead of classified as orphans, since the listing may predate the change. The margin covers clock skew between replicas, the lag between setting timestamps and committing them, and providers listing new resources with a delay.
- STEP 6: Handle orphans according to `DSTACK_SERVER_ORPHAN_CLEANUP_MODE`:
    - `report` (default): log, send to Sentry, and emit an event targeting the owner instance. If the instance was deleted, the event still targets it by the id and name kept in `ProviderRefModel`, so it shows next to the instance's earlier events. Reports are not deduplicated: an orphan that stays is reported again on every cleanup of the backend, at most once per cleanup interval. This is expected and accepted.
    - `delete`: call `delete_resource_group()` and emit an event. If the backend raises `NotYetTerminated` for a group with an owner resource, the owner's deletion was requested and the event says the resources are being deleted. The remaining internal resources are listed and deleted by next cleanups.
    - `off`: the pipeline and enrollment are disabled.
- STEP 7: Set the outcome:
    - Clean (everything listed, nothing skipped, all orphans handled): `clean_at` advances to the listing time minus the margin, and the retry delay is reset.
    - Unsettled (a group skipped, a deletion in progress, or some regions in `ResourceListing.failures`): `clean_at` stays, the retry delay is reset, and the backend is retried after the interval. Listed groups are still handled.
    - Failed (listing raised or a deletion failed): `clean_at` stays and the retry is backed off.

Events are emitted in the lock-guarded apply, so a worker that lost the lock emits nothing.

## Termination give-up

When instance termination gives up after retrying, the log says that orphan cleanup will retry deleting the instance if the mode is `delete` and the backend supports listing. Otherwise, it asks to terminate the instance manually.

## Limitations

- Resources are not cleaned up if the backend credentials change or the backend is deleted.
- Compute groups, placement groups, volumes and gateways are not covered. `OwnerType` only has `INSTANCE`.
- `ProviderRefModel` records are never deleted yet. There is one per fleet instance and per placeholder instance, i.e. per job submission that provisions new capacity.
- On dstack Sky, each project's `dstack` backend lists the shared base backend accounts, so listings repeat per project. Cleaning up each shared account once is a possible optimization.
