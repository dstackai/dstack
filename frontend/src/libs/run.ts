import { get as _get } from 'lodash';
import { StatusIndicatorProps } from '@cloudscape-design/components';

import { IModelExtended } from '../pages/Models/List/types';

export const getStatusIconType = (status: IRun['status']): StatusIndicatorProps['type'] => {
    switch (status) {
        case 'failed':
            return 'error';
        case 'aborted':
        case 'terminated':
            return 'stopped';
        case 'done':
            return 'success';
        case 'running':
        case 'terminating':
            return 'in-progress';
        case 'submitted':
        case 'pending':
        case 'pulling':
        case 'provisioning':
            return 'pending';
        default:
            return 'stopped';
    }
};

export const getExtendedModelFromRun = (run: IRun): IModelExtended | null => {
    if (!run?.service?.model) return null;

    return {
        ...run.service.model,
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
