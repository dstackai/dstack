declare type TInstanceListRequestParams = TBaseRequestListParams & {
    project_names?: string[];
    fleet_ids?: string[];
    only_active?: boolean;
};

declare type TInstanceStatus =
    | 'pending'
    | 'creating'
    | 'starting'
    | 'provisioning'
    | 'idle'
    | 'busy'
    | 'terminating'
    | 'terminated';

declare type THealthStatus = 'healthy' | 'warning' | 'failure';

declare interface IInstance {
    id: string;
    fleet_name: string;
    fleet_id: string;
    backend: TBackendType;
    instance_num: number;
    instance_type: {
        name: string;
        resources: IResources;
    } | null;
    name: string;
    job_name: string | null;
    project_name: string | null;
    job_status: TJobStatus | null;
    hostname: string;
    status: TInstanceStatus;
    unreachable: boolean;
    health_status: THealthStatus;
    termination_reason: string | null;
    termination_reason_message: string | null;
    created: DateTime;
    finished_at: DateTime | null;
    region: string;
    availability_zone: string | null;
    price: number | null;
    total_blocks: number | null;
    busy_blocks: number;
}
