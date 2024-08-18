export const runStatusForDeleting: TJobStatus[] = ['failed', 'aborted', 'done', 'terminated'];
export const runStatusForStopping: TJobStatus[] = ['submitted', 'provisioning', 'pulling', 'pending', 'running'];
export const runStatusForAborting: TJobStatus[] = ['submitted', 'provisioning', 'pulling', 'pending', 'running'];
export const unfinishedRuns: TJobStatus[] = ['running', 'terminating', 'pending'];
