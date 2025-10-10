declare type TAvailability = 'unknown' | 'available' | 'not_available' | 'no_quota' | 'no_balance' | 'idle' | 'busy';

declare type TSpot = 'spot' | 'on-demand' | 'auto';
declare type TGpuGroupBy = 'gpu' | 'backend' | 'region' | 'count';

declare type TRange = {
    min: number;
    max?: number;
};

declare interface IPortMappingRequest {
    local_port?: number;
    container_port: number;
}

declare interface IGPUSpecRequest {
    vendor?: string;
    name?: string[];
    count?: TRange | number | string;
    memory?: TRange | number | string;
    total_memory?: TRange | number | string;
    compute_capability?: any[];
}

declare interface IResourcesSpecRequest {
    cpu?: TRange | number | string;
    memory?: TRange | number | string;
    shm_size?: number | string;
    gpu?: IGPUSpecRequest | number | string;
    disk?: { size: TRange | number | string } | number | string;
}

declare interface ITaskConfigurationQueryParams {
    nodes?: number;
    ports?: Array<number | string | IPortMappingRequest>;
    commands?: string[];
    type: 'task';
    resources?: IResourcesSpecRequest;
    privileged?: boolean;
    home_dir?: string;
    env?: string[] | object;
    volumes?: Array<unknown>;
    docker?: boolean;
    files?: Array<unknown>;
    setup?: string[];
    backends?: TBackendType[];
    regions?: string[];
    availability_zones?: string[];
    instance_types?: string[];
    reservation?: string;
    spot_policy?: TSpot;
    max_price?: number;
}

declare interface IGpu {
    name: string;
    memory_mib: number;
    vendor: string;
    availability: TAvailability[];
    spot: TSpot[];
    count: {
        min: number;
        max: number;
    };
    price: {
        min: number;
        max: number;
    };
    backends?: TBackendType[];
    backend?: TBackendType;
    regions?: string[];
    region?: string;
}

declare type TGpusListQueryParams = {
    project_name: string;
    group_by?: TGpuGroupBy[];
    run_spec: {
        group_gy?: string;
        spot?: string | boolean;
        gpu_vendor?: string;
        gpu_count?: number;
        gpu_memory?: number;
        gpu_name?: string;
        backends?: TBackendType[];
        configuration: ITaskConfigurationQueryParams;
        profile?: { name: string; default?: boolean };
        ssh_key_pub: string;
    };
};

declare type TGpusListQueryResponse = {
    gpus: IGpu[];
};
