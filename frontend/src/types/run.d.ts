declare type TRunsRequestParams = {
    project_name?: IProject['project_name'];
    repo_id?: string;
    username?: string;
    only_active?: boolean;
    prev_submitted_at?: string;
    prev_run_id?: string;
    limit?: number;
    ascending?: boolean;
    job_submissions_limit?: number;
};

declare type TDeleteRunsRequestParams = {
    project_name: IProject['project_name'];
    runs_names: IRun['run_name'][];
};

declare type TStopRunsRequestParams = {
    project_name: IProject['project_name'];
    runs_names: IRun['run_name'][];
    abort: boolean;
};

declare type TJobMetricsRequestParams = {
    project_name: IProject['project_name'];
    run_name: string;
    replica_num?: number;
    job_num: number;
    limit?: number;
    after?: string;
    before?: string;
};

declare type TJobStatus =
    | 'pending'
    | 'submitted'
    | 'provisioning'
    | 'pulling'
    | 'running'
    | 'terminating'
    | 'terminated'
    | 'aborted'
    | 'failed'
    | 'done';

declare type TJobErrorCode =
    | 'failed_to_start_due_to_no_capacity'
    | 'interrupted_by_no_capacity'
    | 'waiting_runner_limit_exceeded'
    | 'container_exited_with_error'
    | 'ports_binding_failed';

declare interface IAppSpec {
    port: number;
    app_name: string;
    map_to_port?: number;
    url_path?: string;
    url_query_params?: { [key: string]: string };
}

declare interface IJobSpec {
    app_specs?: IAppSpec;
    commands: string[];
    env?: { [key: string]: string };
    home_dir?: string;
    image_name: string;
    job_name: string;
    job_num: number;
    max_duration?: number;
    working_dir: string;
}

declare interface IGpu {
    name: string;
    memory_mib: number;
}

declare interface IDisk {
    size_mib: number;
}

declare interface IResources {
    cpus: number;
    memory_mib: number;
    gpus: IGpu[];
    spot: boolean;

    disk?: IDisk;

    description?: string;
}

declare interface InstanceType {
    name: string;
    resources: IResources;
}

declare interface IJobProvisioningData {
    backend: TBackendType;
    instance_type: InstanceType;
    instance_id: string;
    hostname: string;
    region: string;
    price: number;
    username: string;
    ssh_port: number;
    dockerized: boolean;
    backend_data?: string;
}

declare interface IJobSubmission {
    id: string;
    job_provisioning_data?: IJobProvisioningData | null;
    error_code?: TJobErrorCode | null;
    submission_num: number;
    status: TJobStatus;
    submitted_at: number;
    termination_reason?: string | null;
    termination_reason_message?: string | null;
    exit_status?: number | null;
    status_message?: string | null;
    error?: string | null;
}

declare interface IJob {
    job_spec: IJobSpec;
    job_submissions: IJobSubmission[];
}

declare interface IDevEnvironmentConfiguration {
    type: 'dev-environment';
    priority?: number | null
}

declare interface ITaskConfiguration {
    type: 'task';
    priority?: number | null
}

declare interface IServiceConfiguration {
    type: 'service';
    gateway: string | null;
    priority?: number | null
}
declare interface IRunSpec {
    configuration: IDevEnvironmentConfiguration | ITaskConfiguration | IServiceConfiguration;
    configuration_path: string;
    repo_code_hash?: string;
    repo_id: string;
    run_name?: string;
    ssh_key_pub: string;
    working_dir: string;
    repo_data: IRemoteRunRepoData | ILocalRunRepoData | VirtualRunRepoData;
}

declare interface IModel {
    name: string;
    base_url: string;
    type: string;
}

declare interface IRunService {
    url: string;
    model: null | IModel;
}

declare interface IRun {
    id: string;
    project_name: string;
    user: string;
    submitted_at: string;
    terminated_at: string | null;
    status: TJobStatus;
    error?: string | null;
    jobs: IJob[];
    run_spec: IRunSpec;
    latest_job_submission?: IJobSubmission;
    cost: number;
    service: IRunService | null;
    status_message?: string | null;
}

declare interface IMetricsItem {
    name: string;
    timestamps: string[];
    values: number[];
}
