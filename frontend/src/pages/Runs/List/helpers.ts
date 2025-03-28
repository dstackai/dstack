import { groupBy as _groupBy } from 'lodash';

import { getBaseUrl } from 'App/helpers';

import { finishedJobs } from '../constants';
import { getJobStatus } from '../Details/Jobs/List/helpers';

export const getGroupedRunsByProjectAndRepoID = (runs: IRun[]) => {
    return _groupBy(runs, ({ project_name }) => project_name);
};

export const getRunListItemResources = (run: IRun) => {
    if (run.jobs.length > 1) {
        return '-';
    }

    return run.latest_job_submission?.job_provisioning_data?.instance_type?.resources?.description;
};

export const getRunListItemSpotLabelKey = (run: IRun) => {
    if (run.jobs.length > 1) {
        return '-';
    }

    if (run.latest_job_submission?.job_provisioning_data?.instance_type?.resources?.spot) {
        return 'common.yes';
    }

    return 'common.no';
};

export const getRunListItemSpot = (run: IRun) => {
    if (run.jobs.length > 1) {
        return '';
    }

    return run.latest_job_submission?.job_provisioning_data?.instance_type?.resources?.spot?.toString() ?? '-';
};

export const getRunListItemPrice = (run: IRun) => {
    const unFinishedJobs = run.jobs.filter((job) => !finishedJobs.includes(getJobStatus(job)));

    if (run.jobs.length > 1) {
        return `$${unFinishedJobs.reduce<number>((acc, job) => {
            const price = job.job_submissions?.[job.job_submissions.length - 1]?.job_provisioning_data?.price;

            if (price) acc += price;

            return acc;
        }, 0)}`;
    }

    return run.latest_job_submission?.job_provisioning_data?.price
        ? `$${run.latest_job_submission?.job_provisioning_data?.price}`
        : null;
};

export const getRunListItemInstance = (run: IRun) => {
    if (run.jobs.length > 1) {
        return '';
    }

    return run.latest_job_submission?.job_provisioning_data?.instance_type?.name;
};

export const getRunListItemInstanceId = (run: IRun) => {
    if (run.jobs.length > 1) {
        return '';
    }

    return run.latest_job_submission?.job_provisioning_data?.instance_id ?? '-';
};

export const getRunListItemRegion = (run: IRun) => {
    if (run.jobs.length > 1) {
        return '';
    }

    return run.latest_job_submission?.job_provisioning_data?.region ?? '-';
};

export const getRunListItemBackend = (run: IRun) => {
    if (run.jobs.length > 1) {
        return '';
    }

    return run.latest_job_submission?.job_provisioning_data?.backend ?? '-';
};

export const getRunListItemServiceUrl = (run: IRun) => {
    const url = run.service?.url;
    if (!url) return null;
    return url.startsWith('/') ? `${getBaseUrl()}${url}` : url;
};
