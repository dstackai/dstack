export type RunsRequestParams = {
    name: IProject['project_name'];
    repo_id?: string;
    run_name?: string;
    include_request_heads?: boolean;
};
