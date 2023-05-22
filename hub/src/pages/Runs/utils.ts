import { runStatusForAborting, runStatusForDeleting, runStatusForStopping } from './constants';

export const isAvailableDeletingForRun = (run: IRun): boolean => {
    return runStatusForDeleting.includes(run.status);
};

export const isAvailableStoppingForRun = (run: IRun): boolean => {
    return runStatusForStopping.includes(run.status);
};

export const isAvailableAbortingForRun = (run: IRun): boolean => {
    return runStatusForAborting.includes(run.status);
};
