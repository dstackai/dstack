
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
    run_name: IRun['run_name'],
    prefix: string,
    recursive?: boolean
}
