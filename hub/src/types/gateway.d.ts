declare interface IGateway {
    backend: string,
    head: {
        instance_name: string,
        external_ip: string,
        internal_ip: string,
        created_at?: number,
        region?: string,
        wildcard_domain?: string
    },
    default: boolean
}

declare type TGatewayBackendsListResponse = {
    backend: string,
    regions: string[],
}[]

declare type TCreateGatewayParams = {
    backend: string,
    region?: string,
}

declare type TUpdateGatewayParams = {
    wildcard_domain?: string,
    default?: boolean,
}

declare interface IGatewayBackend {
    backend: string,
    region?: string,
    wildcard_domain?: string
    default?: boolean
}
