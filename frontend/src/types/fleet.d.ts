declare type TSpotPolicy = 'spot' | 'on-demand' | 'auto';

declare type TFleetListRequestParams = TBaseRequestListParams & {
    project_name?: string;
    only_active?: boolean;
};

declare interface ISSHHostParamsRequest {
    hostname: string;
    port?: number;
    user?: string;
    identity_file?: string;
    ssh_key?: {
        public: string;
        private?: string;
    };
}

declare interface ISSHConfig {
    user?: string;
    port?: number;
    identity_file?: string;
    ssh_key?: {
        public: string;
        private?: string;
    };
    hosts: (ISSHHostParamsRequest | string)[];
    network?: string;
}

declare interface IFleetConfigurationResource {
    cpu: string;
    memory: string;
    shm_size: number;
    gpu: string;
    disk: string;
}

declare interface IFleetConfigurationRequest {
    type?: 'fleet';
    name?: string;
    ssh_config?: ISSHConfig;
    nodes?: {
        min?: number;
        max?: number;
    };
    placement?: 'any' | 'cluster';
    resources?: IFleetConfigurationResource[];
    backends?: TBackendType[];
    regions?: string[];
    instance_types?: string[];
    spot_policy?: TSpotPolicy;
    retry?:
        | {
              on_events: ('no-capacity' | 'interruption' | 'error')[];
              duration?: number | string;
          }
        | boolean;
    max_price?: number;
    idle_duration?: number | string;
}

declare interface IProfileRequest {
    backends?: TBackendType[];
    regions?: string[];
    instance_types?: string[];
    spot_policy?: TSpotPolicy;
    // retry?: components["schemas"]["ProfileRetryRequest"] | boolean;
    retry_policy?: {
        retry?: boolean;
        duration?: number | string;
    };
    max_duration?: 'off' | string | number;
    max_price?: number;
    pool_name?: string;
    instance_name?: string;
    creation_policy?: 'reuse' | 'reuse-or-create';
    idle_duration?: number | string;
    name: string;
    default?: boolean;
}

declare interface IFleetSpec {
    autocreated: boolean;
    configuration: IFleetConfigurationRequest;
    profile: IProfileRequest;
}

declare interface IFleet {
    id: string;
    created_at: string;
    instances: IInstance[];
    name: string;
    project_name: string;
    spec: IFleetSpec;
    status: 'submitted' | 'active' | 'terminating' | 'terminated' | 'failed';
    status_message: string;
}
