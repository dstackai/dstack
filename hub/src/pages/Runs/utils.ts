import { runStatusForAborting, runStatusForDeleting, runStatusForStopping } from './constants';

export const isAvailableDeletingForRun = (status: IRunHead['status']): boolean => {
    return runStatusForDeleting.includes(status);
};

export const isAvailableStoppingForRun = (status: IRunHead['status']): boolean => {
    return runStatusForStopping.includes(status);
};

export const isAvailableAbortingForRun = (status: IRunHead['status']): boolean => {
    return runStatusForAborting.includes(status);
};
