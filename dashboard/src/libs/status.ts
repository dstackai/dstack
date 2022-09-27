export const finishedStatuses = new Set<TStatus>(['stopped', 'aborted', 'failed', 'done']);
export const availableResumeStatuses = new Set<TStatus>(['stopped', 'aborted']);
export const failedStatuses = new Set<TStatus>(['failed', 'aborted']);
export const runningStatuses = new Set<TStatus>(['submitted', 'uploading', 'downloading', 'running', 'queued']);

export const isFinishedStatus = (status: TStatus): boolean => {
    return finishedStatuses.has(status);
};

export const isRunningStatus = (status: TStatus): boolean => {
    return runningStatuses.has(status);
};

export const isAvailableResumeByStatus = (status: TStatus): boolean => {
    return availableResumeStatuses.has(status);
};

export const isFailedStatus = (status: TStatus): boolean => {
    return failedStatuses.has(status);
};
