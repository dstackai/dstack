export const getJobSubmissionId = (run?: IRun): string | undefined => {
    if (!run) return;

    const lastJob = run.jobs[run.jobs.length - 1];

    if (!lastJob) return;

    return lastJob.job_submissions[lastJob.job_submissions.length - 1]?.id;
};
