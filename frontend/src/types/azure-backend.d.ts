declare interface IAzureBackendValues {
    type: AzureCredentialTypeEnum.CLIENT,
    default_creds: boolean,
    tenant_id: TBackendValueField,
    subscription_id: TBackendValueField,
    locations: TBackendValueField<string[]>,
}

enum AzureCredentialTypeEnum {
    DEFAULT = 'default',
    CLIENT = 'client'
}

declare type TAzureClientCreds = {
    type: AzureCredentialTypeEnum.CLIENT,
    client_id?: string,
    client_secret?: string,
    tenant_id?: string
}

declare type TAzureDefaultCreds = {
    type: AzureCredentialTypeEnum.DEFAULT
}

declare interface IBackendAzure {
    type: 'azure',
    tenant_id: string,
    creds: TAzureClientCreds | TAzureDefaultCreds
    subscription_id: string,
    locations: string[],
}
