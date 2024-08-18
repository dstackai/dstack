declare interface IGateway {
    backend: string,
    name: string,
    ip_address: string,
    instance_id: string,
    region:string
    wildcard_domain?: string
    default: boolean
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
