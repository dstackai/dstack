declare interface IRunWorkflowsFetchParams {
    count: number;
    userName?: string;
    repoName?: string;
    repoUserName?: string;
    tagName?: string
}
declare interface IRunWorkflowFetchParams {
    repoUserName?: string;
    repoName?: string;
    runName?: string;
}

declare interface IWorkflowPort {
    host_name: string,
    port: string
}

declare interface IAvailabilityIssues {
    timestamp: null | number,
    message: null | string
}

declare interface IRunWorkflow extends Pick<IRun, 'run_name' | 'status' | 'submitted_at' | 'tag_name' | 'updated_at' | 'user_name' | 'workflow_name' | 'repo_hash' | 'repo_branch' | 'repo_name' | 'repo_user_name' | 'repo_diff' | 'variables'> {
    artifacts: IArtifact[]
    availability_issues?: IAvailabilityIssues[]
    ports: IWorkflowPort[]
    apps: TApps | null
    provider_name?: string | null
}

declare type WorkflowGroupByRunName = Array<[IRunWorkflow['run_name'], IRunWorkflow[]]>
