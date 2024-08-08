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
    backend: TBackendType,
    instance_type: {
        name: string,
        resources: IResources
    },
    name: string,
    job_name: string | null,
    project_name: string | null,
    job_status: TJobStatus | null,
    hostname: string,
    status: TInstanceStatus,
    created: string,
    region: string,
    price: number | null
}

declare interface IPool {
    name: string,
    instances: IInstance[]
}

declare interface IPoolListItemExtended extends IInstance {
    pool_name: string
}

declare interface IPoolListItem {
    name: string,
    default: boolean,
    created_at: string,
    total_instances: number,
    available_instances: number
}

declare interface IInstanceListItem extends IInstance {
    id: string;
    pool_name: string
}

declare type TPoolInstancesRequestParams = {
    project_name?: IProject['project_name'];
    pool_name?: string,
    only_active?: boolean,
    prev_created_at?: string,
    prev_id?: string,
    limit?: number,
    ascending?: boolean,
};
