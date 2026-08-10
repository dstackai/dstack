declare interface IGatewayReplica {
    hostname: string,
    backend: string,
    region: string,
}

declare interface IGateway {
    name: string,
    project_name?: string,
    ip_address: string,
    instance_id: string,
    hostname?: string,
    wildcard_domain?: string
    default: boolean
    replicas: IGatewayReplica[],
    created_at?: number,
}

declare type TGatewayBackendsListResponse = {
    backend: string,
    regions: string[],
}[]

declare type TCreateGatewayParams = {
    backend_type: string,
    region?: string,
}

declare type TUpdateGatewayParams = {
    wildcard_domain?: string,
    default?: boolean,
}
