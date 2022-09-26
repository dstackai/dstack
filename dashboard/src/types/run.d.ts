declare interface IRun {
    user_name: string,
    run_name: string,
    workflow_name: string | null,
    repo_branch: string,
    repo_hash: string,
    repo_diff: null | string,
    repo_name: string,
    repo_user_name: string,
    provider_name: string | null
    variables: TVariables,
    submitted_at: number,
    started_at: null | number,
    finished_at: null | number,
    status: TStatus,
    runner_id: string,
    runner_user_name: null | string,
    runner_name: string | null,
    updated_at: number,
    tag_name: null | string
    number_of_finished_jobs: number
    number_of_unfinished_jobs: number
}

declare interface IRunsFetchParams {
    count: number;
    repoUrl?: string;
    runName?: string
}
