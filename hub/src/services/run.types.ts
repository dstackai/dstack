export type RunsRequestParams = {
    name: IProject['project_name'];
    repo_id?: string;
    run_name?: string;
    include_request_heads?: boolean;
};

export type DeleteRunsRequestParams = {
    name: IProject['project_name'];
    repo_id?: string;
    run_names: IRun['run_name'][];
};

export type StopRunsRequestParams = {
    name: IProject['project_name'];
    repo_id?: string;
    run_names: IRun['run_name'][];
    abort: boolean;
};
