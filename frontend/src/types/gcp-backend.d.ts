enum GCPCredentialTypeEnum {
    DEFAULT = 'default',
    SERVICE_ACCOUNT = 'service_account'
}

declare type TGCPServiceAccountCreds = {
    type: GCPCredentialTypeEnum.SERVICE_ACCOUNT,
    filename?: string,
    data?: string,
}

declare type TGCPDefaultCreds = {
    type: GCPCredentialTypeEnum.DEFAULT
}

declare interface IGCPBackendValues {
    type: 'gcp',
    default_creds: boolean,
    regions: TBackendValueField<string[]>,
    project_id: TBackendValueField,
}

declare interface IBackendGCP {
    type: 'gcp',
    creds: TGCPServiceAccountCreds | TGCPDefaultCreds,
    regions: string[],
    project_id: string,
}
