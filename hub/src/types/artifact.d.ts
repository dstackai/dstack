
declare interface IArtifactFile {
    filepath: string,
    filesize_in_bytes: number | null
}
declare interface IArtifact {
    job_id: string,
    name: string,
    path: string,

    files: IArtifactFile[]
}

declare type TRequestArtifactListParams = {
    name: IProject['project_name'],
    repo_id: IRepo['repo_id'],
    run_name: IRun['run_name'],
    prefix: string,
    recursive?: boolean
}
