declare type TTagsRequestParams = {
    project_name: IProject["project_name"]
    repo_id: IRepo['repo_id']
}

declare type TTagRequestParams = {
    project_name: IProject["project_name"]
    repo_id: IRepo['repo_id']
    tag_name: string
}

declare interface ITag {
    repo_id: string,
    tag_name: string,
    run_name: string,
    workflow_name: string,
    provider_name: string,
    hub_user_name: string,
    created_at: DateTime,
    artifact_heads: {
        job_id: string,
        artifact_path: string
    }[]
}
