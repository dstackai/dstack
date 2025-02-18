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
    created: DateTime;
    region: string;
    price: number | null;
}
