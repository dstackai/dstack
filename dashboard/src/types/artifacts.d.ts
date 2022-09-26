declare type TArtifactPath = string;
declare type TArtifactPaths = null | TArtifactPath[];

declare interface IArtifact {
    job_id: string,
    artifact_path: string
}

declare type TArtifacts = IArtifact[];

declare interface IArtifactObject {
    name: string,
    folder: boolean
}

declare interface IArtifactsGeneralTableCellData {
    artifacts: TArtifactPaths;
}
declare interface IJobArtifactsTableCellData extends Pick<IJob, 'job_id'>, IArtifactsGeneralTableCellData {}
declare interface IWorkflowArtifactsTableCellData extends Pick<IRunWorkflow, 'run_name' | 'workflow_name'>, IArtifactsGeneralTableCellData {}

declare interface IArtifactsFetchParams {
    repo_user_name: string,
    repo_name: string,
    job_id: string
    path: string
}

