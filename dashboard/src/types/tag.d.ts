declare type  TFetchTagsRequestParams = {
    repoUserName: string,
    repoName: string,
}

declare type  TFetchTagRequestParams = {
    repoUserName: string,
    repoName: string,
    tagName: string,
}

declare type  TAddTagRequestParams = {
    repo_user_name: string,
    repo_name: string,
    tag_name: string,
    run_name: string,
}

declare type  TDeleteTagRequestParams = {
    repo_user_name: string,
    repo_name: string,
    tag_name: string,
}

declare type TTagArtifactHead = {
    job_id: string,
    artifact_path: string
}

declare interface ITag {
    repo_user_name: string,
    repo_name: string,
    tag_name: string,
    run_name: string,
    workflow_name: string,
    provider_name: string,
    created_at: number,
    artifact_heads: TTagArtifactHead[]
}
