import { get as _get } from 'lodash';
import { StatusIndicatorProps } from '@cloudscape-design/components';

import { capitalize } from 'libs';
import { formatResources } from 'libs/resources';

import { finishedRunStatuses } from '../pages/Runs/constants';
import { getJobProbesStatuses } from '../pages/Runs/Details/Jobs/List/helpers';

import { IModelExtended } from '../pages/Models/List/types';

export const getStatusIconType = (
    status: IRun['status'] | TJobStatus,
    terminationReason: string | null | undefined,
): StatusIndicatorProps['type'] => {
    if (finishedRunStatuses.includes(status) && terminationReason === 'interrupted_by_no_capacity') {
        return 'stopped';
    }
    switch (status) {
        case 'failed':
            return 'error';
        case 'done':
            return 'success';
        case 'aborted':
        case 'terminated':
            return 'stopped';
        case 'running':
            return 'success';
        case 'terminating':
        case 'pulling':
        case 'provisioning':
            return 'in-progress';
        case 'submitted':
        case 'pending':
            return 'pending';
        default:
            console.error(new Error('Undefined run status'));
    }
};

export const getStatusIconColor = (
    status: IRun['status'] | TJobStatus,
    terminationReason: string | null | undefined,
    statusMessage: string,
): StatusIndicatorProps.Color | undefined => {
    if (statusMessage === 'No fleets') {
        return 'red';
    }
    if (terminationReason === 'failed_to_start_due_to_no_capacity' || terminationReason === 'interrupted_by_no_capacity') {
        return 'yellow';
    }
    switch (status) {
        case 'submitted':
        case 'pending':
        case 'provisioning':
        case 'pulling':
        case 'terminating':
            return 'blue';
        case 'aborted':
            return 'yellow';
        case 'done':
            return 'grey';
        default:
            return undefined;
    }
};

/**
 * A finished run shows the status and the termination reason of its latest job submission.
 */
export const getRunStatus = (run: IRun) => {
    const isFinished = finishedRunStatuses.includes(run.status);

    return {
        status: isFinished ? (run.latest_job_submission?.status ?? run.status) : run.status,
        terminationReason: isFinished ? run.latest_job_submission?.termination_reason : null,
    };
};

export const getRunStatusMessage = (run: IRun): string => {
    if (finishedRunStatuses.includes(run.status) && run.latest_job_submission?.status_message) {
        return capitalize(run.latest_job_submission.status_message);
    } else {
        return capitalize(run.status_message || run.status);
    }
};

export const getRunError = (run: IRun): string | null => {
    const error = run.error ?? run.latest_job_submission?.error ?? null;
    return error ? capitalize(error) : null;
};

export const getRunProbeStatuses = (run: IRun): StatusIndicatorProps.Type[] => {
    const job = run.jobs[0];

    if (!job) {
        return [];
    }

    return getJobProbesStatuses(run.jobs[0]);
};

export const getRunPriority = (run: IRun): number | null => {
    return run.run_spec.configuration?.priority ?? null;
};

export const getExtendedModelFromRun = (run: IRun): IModelExtended | null => {
    const model = run?.service?.model;

    if (!model) return null;

    const { status, terminationReason } = getRunStatus(run);

    return {
        name: model.name,
        project_name: run.project_name,
        // A finished run keeps its URL: the model is back at it when the service is applied again
        endpoints: [{ project_name: run.project_name, base_url: model.base_url }],
        run: {
            id: run.id,
            run_name: run?.run_spec.run_name ?? 'No run name',
            status,
            termination_reason: terminationReason,
            status_message: getRunStatusMessage(run),
            user: run.user,
            resources: run.latest_job_submission?.job_provisioning_data?.instance_type?.resources
                ? formatResources(run.latest_job_submission.job_provisioning_data.instance_type.resources)
                : null,
            price: run.latest_job_submission?.job_provisioning_data?.price ?? null,
            submitted_at: run.submitted_at,
            repository: getRepoNameFromRun(run),
            backend: run.latest_job_submission?.job_provisioning_data?.backend ?? null,
        },
    };
};

export const getRepoNameFromRun = (run: IRun): string => {
    return _get(run.run_spec.repo_data, 'repo_name', _get(run.run_spec.repo_data, 'repo_dir', '-'));
};
