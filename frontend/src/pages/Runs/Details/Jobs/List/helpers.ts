import { format } from 'date-fns';
import type { StatusIndicatorProps } from '@cloudscape-design/components/status-indicator';

import { DATE_TIME_FORMAT } from 'consts';
import { capitalize } from 'libs';
import { formatBackend } from 'libs/fleet';
import { formatResources } from 'libs/resources';

export const getJobListItemResources = (job: IJob) => {
    const resources = job.job_submissions?.[job.job_submissions.length - 1]?.job_provisioning_data?.instance_type?.resources;
    return resources ? formatResources(resources) : '-';
};

export const getJobListItemSpot = (job: IJob) => {
    return (
        job.job_submissions?.[
            job.job_submissions.length - 1
        ]?.job_provisioning_data?.instance_type?.resources?.spot?.toString() ?? '-'
    );
};

export const getJobListItemPrice = (job: IJob) => {
    return job.job_submissions?.[job.job_submissions.length - 1]?.job_provisioning_data?.price
        ? `$${job.job_submissions?.[job.job_submissions.length - 1]?.job_provisioning_data?.price}`
        : null;
};

export const getJobListItemInstance = (job: IJob) => {
    return job.job_submissions?.[job.job_submissions.length - 1]?.job_provisioning_data?.instance_type?.name;
};

export const getJobListItemRegion = (job: IJob) => {
    return job.job_submissions?.[job.job_submissions.length - 1]?.job_provisioning_data?.region ?? '-';
};

export const getJobListItemBackend = (job: IJob) => {
    return formatBackend(job.job_submissions?.[job.job_submissions.length - 1]?.job_provisioning_data?.backend);
};

export const getJobSubmittedAt = (job: IJob) => {
    return job.job_submissions?.[job.job_submissions.length - 1].submitted_at
        ? format(new Date(job.job_submissions?.[job.job_submissions.length - 1].submitted_at), DATE_TIME_FORMAT)
        : '';
};

export const getJobFinishedAt = (job: IJob) => {
    const finished_at = job.job_submissions?.[job.job_submissions.length - 1].finished_at;
    return finished_at ? format(new Date(finished_at), DATE_TIME_FORMAT) : '';
};

export const getJobStatus = (job: IJob) => {
    return job.job_submissions?.[job.job_submissions.length - 1].status;
};

export const getJobSubmissionProbes = (job: IJob) => {
    return job.job_submissions?.[job.job_submissions.length - 1].probes;
};

export const getJobProbesStatuses = (job: IJob): StatusIndicatorProps.Type[] => {
    const status = getJobStatus(job);
    const probes = getJobSubmissionProbes(job);

    if (!probes?.length || status !== 'running') {
        return [];
    }

    return probes.map((probe, index) => {
        if (job.job_spec?.probes?.[index] && probe.success_streak >= job.job_spec.probes[index].ready_after) {
            return 'success';
        } else if (probe.success_streak > 0) {
            return 'in-progress';
        }
        return 'not-started';
    });
};

export const getJobTerminationReason = (job: IJob) => {
    return job.job_submissions?.[job.job_submissions.length - 1].termination_reason ?? '-';
};

export const getJobStatusMessage = (job: IJob): string | null => {
    const latest_submission = job.job_submissions?.[job.job_submissions.length - 1];
    if (latest_submission?.status_message) {
        return capitalize(latest_submission.status_message);
    } else {
        return capitalize(latest_submission.status);
    }
};

export const getJobError = (job: IJob): string | null => {
    return job.job_submissions?.[job.job_submissions.length - 1]?.error ?? null;
};
