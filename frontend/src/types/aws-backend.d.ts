enum AWSCredentialTypeEnum {
    DEFAULT = 'default',
    ACCESS_KEY = 'access_key'
}

declare type WSDefaultCreds = {
    type: AWSCredentialTypeEnum.DEFAULT
}

declare type AWSAccessKeyCreds = {
    type: AWSCredentialTypeEnum.ACCESS_KEY,
    access_key: string,
    secret_key: string,
}

declare interface IAwsBackendValues {
    type: 'aws',
    default_creds: boolean
    regions: TBackendValueField<string[]>,
    creds?:  AWSAccessKeyCreds | WSDefaultCreds,
}

declare type TAwsBucket = {
    name: string;
    created?: string;
    region?: string;
}

declare interface IBackendAWS {
    type: 'aws',
    creds:  AWSAccessKeyCreds | WSDefaultCreds,
    regions: string[],
    vpc_name?: string,
}
