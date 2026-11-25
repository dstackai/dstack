export interface IModelEndpoint {
    project_name: IProject['project_name'];
    base_url: string | null;
}

export interface IModelRun {
    id: string;
    run_name: string;
    status: TJobStatus;
    termination_reason?: string | null;
    status_message: string;
    submitted_at: string;
    user: string;
    resources: string | null;
    price: number | null;
    repository: string | null;
    backend: TBackendType | null;
}

export interface IModelExtended {
    name: string;
    // The project that runs the model
    project_name: IProject['project_name'];
    // The model endpoints of the user's projects that have the model
    endpoints: IModelEndpoint[];
    // An imported model has no run in the user's projects
    run?: IModelRun;
}

export type TModelsFilters = Pick<TRunsRequestParams, 'project_name' | 'username'>;

export type TModelsRequestParams = TModelsFilters & Pick<TRunsRequestParams, 'only_active'>;
