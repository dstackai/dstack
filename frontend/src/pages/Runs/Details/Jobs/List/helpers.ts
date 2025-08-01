import { format } from 'date-fns';

import { DATE_TIME_FORMAT } from 'consts';
import { capitalize } from 'libs';

export const getJobListItemResources = (job: IJob) => {
    return job.job_submissions?.[job.job_submissions.length - 1]?.job_provisioning_data?.instance_type?.resources?.description;
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
    return job.job_submissions?.[job.job_submissions.length - 1]?.job_provisioning_data?.backend ?? '-';
};

export const getJobSubmittedAt = (job: IJob) => {
    return job.job_submissions?.[job.job_submissions.length - 1].submitted_at
        ? format(new Date(job.job_submissions?.[job.job_submissions.length - 1].submitted_at), DATE_TIME_FORMAT)
        : '';
};

export const getJobStatus = (job: IJob) => {
    return job.job_submissions?.[job.job_submissions.length - 1].status;
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
