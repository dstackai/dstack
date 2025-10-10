import { get as _get } from 'lodash';
import jsYaml from 'js-yaml';
import { StatusIndicatorProps } from '@cloudscape-design/components';

import { capitalize } from 'libs';

import { finishedRunStatuses } from '../pages/Runs/constants';

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
): StatusIndicatorProps.Color | undefined => {
    if (terminationReason === 'failed_to_start_due_to_no_capacity' || terminationReason === 'interrupted_by_no_capacity') {
        return 'yellow';
    }
    switch (status) {
        case 'submitted':
        case 'pending':
            return 'blue';
        case 'pulling':
            return 'green';
        case 'aborted':
            return 'yellow';
        case 'done':
            return 'grey';
        default:
            return undefined;
    }
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

export const getRunPriority = (run: IRun): number | null => {
    return run.run_spec.configuration?.priority ?? null;
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

const isMemory = (value: string) => /^\d+GB/.test(value);
const isCount = (value: string) => /^\d+(?:\.\.)*(?:\d+)*$/.test(value);

const parseRange = (rangeString: string) => {
    const [min, max] = rangeString.split('..');

    if (!min && !max) {
        return rangeString;
    }

    return {
        ...(min ? { min } : {}),
        ...(max ? { max } : {}),
    };
};

export const getRunSpecConfigurationResources = (json: unknown): TDevEnvironmentConfiguration['resources'] => {
    const { gpu, ...otherFields } = (json ?? {}) as { [key: string]: unknown };

    const [gpuName, gpuMemoryOrCount, gpuCount] = ((gpu as string) ?? '').split(':');

    const gpuResources: TGPUResources = {};

    if (gpuName) {
        gpuResources.name = gpuName;
    }

    if (isMemory(gpuMemoryOrCount)) {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-expect-error
        gpuResources.memory = parseRange(gpuMemoryOrCount);
    }

    if (isCount(gpuMemoryOrCount)) {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-expect-error
        gpuResources.count = parseRange(gpuMemoryOrCount);
    }

    if (isCount(gpuCount)) {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-expect-error
        gpuResources.count = parseRange(gpuCount);
    }

    return {
        gpu: gpuResources,
        ...otherFields,
    };
};

export const getRunSpecFromYaml = async (yaml: string) => {
    const { name, ...otherFields } = await jsYaml.load(yaml);

    const runSpec: TRunSpec = {
        run_name: name as string,
        configuration: {} as TDevEnvironmentConfiguration,
    };

    Object.keys(otherFields).forEach((key) => {
        switch (key) {
            case 'ide':
                runSpec.configuration.ide = otherFields[key];
                break;
            case 'resources':
                runSpec.configuration.resources = getRunSpecConfigurationResources(otherFields[key]);
                break;
            default:
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                runSpec.configuration[key] = otherFields[key];
                return {};
        }
    });

    return runSpec;
};
