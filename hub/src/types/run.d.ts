declare type TRunStatus = "done" | string

declare interface IRunJobHead {
    job_id: string,
    repo_ref: {
        repo_type: string,
        repo_id: string,
        repo_user_id: string
    },
    run_name: string,
    workflow_name: null | string,
    provider_name: string,
    status: string | "done",
    error_code: null,
    container_exit_code: null,
    submitted_at: number,
    artifact_paths: null,
    tag_name: null,
    app_names: string[]
}

declare interface IRun {
    run_name: string,
    workflow_name: string | null,
    provider_name: string | null,
    repo_user_id: string,
    artifact_heads: null | {
        job_id: string
        artifact_path: string
    }[],
    status: TRunStatus,
    submitted_at: number,
    tag_name: string | null,
    "app_heads": null |
    {
        job_id: string
        artifact_path: string
    }[],
    request_heads: string | null,
    job_heads: IRunJobHead[]
}
