declare type TArtifactPath = string;
declare type TArtifactPaths = null | TArtifactPath[];

declare type IArtifact = {
    job_id: string,
    artifact_path: string
};

declare interface IArtifactObject {
    name: string,
    folder: boolean
}

declare interface IArtifactsGeneralTableCellData {
    artifacts: TArtifactPaths;
}
declare interface IJobArtifactsTableCellData extends Pick<IJob, 'job_id'>, IArtifactsGeneralTableCellData {}
declare interface IWorkflowArtifactsTableCellData extends Pick<IRunWorkflow, 'run_name' | 'workflow_name'>, IArtifactsGeneralTableCellData {}

declare type IArtifactsTableCellData = IJobArtifactsTableCellData | IWorkflowArtifactsTableCellData

declare interface ArtifactsGeneralFetchParams {
    apiUrl: string;
    path: string
}
declare interface IJobArtifactsFetchParams extends Pick<IJob, 'job_id'>, ArtifactsGeneralFetchParams {}
declare interface IWorkflowArtifactsFetchParams extends Pick<IRunWorkflow, 'run_name' | 'workflow_name'>, ArtifactsGeneralFetchParams {}

declare type TArtifactsFetchParams = IJobArtifactsFetchParams | IWorkflowArtifactsFetchParams

