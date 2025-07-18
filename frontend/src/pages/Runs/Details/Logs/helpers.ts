export const getJobSubmissionId = (run?: IRun): string | undefined => {
    if (!run) return;

    const lastJob = run.jobs[run.jobs.length - 1];

    if (!lastJob) return;

    return lastJob.job_submissions[lastJob.job_submissions.length - 1]?.id;
};

export const decodeLogs = (logs: ILogItem[]): ILogItem[] => {
    return logs.map((log: ILogItem) => {
        let { message } = log;

        try {
            message = atob(message);
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
        } catch (e) {
            return log;
        }

        return { ...log, message };
    });
};
