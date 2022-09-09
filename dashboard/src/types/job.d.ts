declare interface IJobGpu {
    name: string | null;
    count: number | null;
    memory: null| number;
}

declare interface IJobRequirements {
    cpu: null | {
        count: null | number;
    },
    memory: number | null;
    shm_size: number | null;
    gpu: null | IJobGpu;
    interruptible?: boolean;
}

declare interface IJob {
    user_name: string
    job_id: string
    run_name: string
    workflow_name: string
    previous_job_ids: null | string[]
    repo_url: string,
    repo_branch: string,
    repo_hash: string,
    repo_diff: string,
    variables: TVariables,
    user_artifacts_s3_bucket: null | string,
    submitted_at: number,
    started_at: null | number,
    finished_at: null | number,
    status: TStatus,
    runner_id: null | string,
    runner_user_name: null | string,
    runner_name: string | null,
    updated_at: number,
    artifact_paths: TArtifactPaths,
    requirements: null | IJobRequirements
}

declare interface IJobsFetchParams {
    userName?: string,
    repoUrl?: string,
    runName?: string,
    workflowName?: string,
    count: number,
}
