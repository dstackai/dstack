import { inActiveRunStatuses, runStatusForAborting, runStatusForDeleting, runStatusForStopping } from './constants';

export const isAvailableDeletingForRun = (status: IRun['status']): boolean => {
    return runStatusForDeleting.includes(status);
};

export const isAvailableStoppingForRun = (status: IRun['status']): boolean => {
    return runStatusForStopping.includes(status);
};

export const runIsStopped = (status: IRun['status']): boolean => {
    return inActiveRunStatuses.includes(status);
};

export const isAvailableAbortingForRun = (status: IRun['status']): boolean => {
    return runStatusForAborting.includes(status);
};

export const getRunProvisioningData = (run: IRun): IJobProvisioningData | void => {
    return run?.latest_job_submission?.job_provisioning_data ?? undefined;
};
