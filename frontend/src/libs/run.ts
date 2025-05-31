import { get as _get } from 'lodash';
import { StatusIndicatorProps } from '@cloudscape-design/components';

import { IModelExtended } from '../pages/Models/List/types';

export const getStatusIconType = (status: IRun['status'] | TJobStatus): StatusIndicatorProps['type'] => {
    console.log('status', status);
    switch (status) {
        case 'failed':
            return 'error';
        case 'aborted':
        case 'terminated':
        case 'done':
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

export const getStatusIconColor = (status: IRun['status'] | TJobStatus, termination_reason: string | null | undefined): StatusIndicatorProps.Color | undefined => {
    if (termination_reason === 'failed_to_start_due_to_no_capacity') {
        return 'yellow';
    }

    switch (status) {
        case 'aborted':
            return 'yellow'
        default:
            return undefined;
    }
};


const capitalize = (str: string): string => str.charAt(0).toUpperCase() + str.slice(1);

export const getJobSubmissionStatus = (run: IRun): string => {
    if (!run.latest_job_submission) {
        return capitalize(run.status);
    }

    const { status, termination_reason, exit_status } = run.latest_job_submission;

    if (status === 'done') {
        return 'Exited (0)';
    }

    if (status === 'failed') {
        switch (termination_reason) {
            case 'container_exited_with_error':
                return `Exited (${exit_status})`;
            case 'failed_to_start_due_to_no_capacity':
                return 'No offers';
            case 'interrupted_by_no_capacity':
                return 'Interrupted';
            default:
                return capitalize(status);
        }
    }

    if (status === 'terminated') {
        switch (termination_reason) {
            case 'terminated_by_user':
                return 'Stopped';
            case 'aborted_by_user':
                return 'Aborted';
            default:
                return capitalize(status);
        }
    }

    return status;
};

export const getExtendedModelFromRun = (run: IRun): IModelExtended | null => {
    if (!run?.service?.model) return null;

    return {
        ...(run.service?.model ?? {}),
        id: run.id,
        project_name: run.project_name,
        run_name: run?.run_spec.run_name ?? 'No run name',
        user: run.user,
        resources: run.latest_job_submission?.job_provisioning_data?.instance_type?.resources?.description ?? null,
        price: run.latest_job_submission?.job_provisioning_data?.price ?? null,
        submitted_at: run.submitted_at,
        repository: getRepoNameFromRun(run),
        backend: run.latest_job_submission?.job_provisioning_data?.backend ?? null,
        region: run.latest_job_submission?.job_provisioning_data?.region ?? null,
    };
};

export const getRepoNameFromRun = (run: IRun): string => {
    return _get(run.run_spec.repo_data, 'repo_name', _get(run.run_spec.repo_data, 'repo_dir', '-'));
};
