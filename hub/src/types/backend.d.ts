declare type TBackendType = 'aws' | 'gcp' | 'azure' | 'lambda' | 'local';

type TBackendValueField<TSelectedType = string, TValuesType = { value: string, label: string}[]> = {
    selected?: TSelectedType,
    values: TValuesType
} | null;


declare interface IAwsBackendValues {
    default_credentials: boolean
    regions: TBackendValueField<string[]>,
    s3_bucket_name: TBackendValueField<string, TAwsBucket[]>,
    ec2_subnet_id: TBackendValueField,
}

declare interface IAzureBackendValues {
    default_credentials: boolean,
    tenant_id: TBackendValueField,
    subscription_id: TBackendValueField,
    locations: TBackendValueField<string[]>,
    storage_account: TBackendValueField,
}

declare interface TVPCSubnetValue { label: string, vpc: string, subnet: string}

declare interface IGCPBackendValues {
    default_credentials: boolean,
    bucket_name: TBackendValueField,
    regions: TBackendValueField<string[]>,
    vpc_subnet: TBackendValueField<string, TVPCSubnetValue[]>
}

declare interface ILambdaBackendValues {
    regions: TBackendValueField<string[]>,
    storage_backend_type: TBackendValueField,
    storage_backend_values:  null | {
        bucket_name: TBackendValueField
    },
}

declare type TBackendValuesResponse = IAwsBackendValues & IAzureBackendValues & IGCPBackendValues & ILambdaBackendValues


declare type TAwsBucket = {
    name: string;
    created?: string;
    region?: string;
}

enum AWSCredentialTypeEnum {
    DEFAULT = 'default',
    ACCESS_KEY = 'access_key'
}
declare interface IBackendAWS {
    type: 'aws',
    credentials: {
        type: AWSCredentialTypeEnum.ACCESS_KEY,
        access_key: string,
        secret_key: string,
    } | {type: AWSCredentialTypeEnum.DEFAULT},
    regions: string[],
    s3_bucket_name: string,
    ec2_subnet_id: string | null,
}

enum AzureCredentialTypeEnum {
    DEFAULT = 'default',
    CLIENT = 'client'
}

declare interface IBackendAzure {
    type: 'azure',
    tenant_id: string,
    credentials: {
        type: AzureCredentialTypeEnum.CLIENT,
        client_id?: string,
        client_secret?: string,
    } | {type: AzureCredentialTypeEnum.DEFAULT}
    subscription_id: string,
    locations: string[],
    storage_account: string,
}

enum GCPCredentialTypeEnum {
    DEFAULT = 'default',
    SERVICE_ACCOUNT = 'service_account'
}

declare interface IBackendGCP {
    type: 'gcp',
    credentials: {
        type: GCPCredentialTypeEnum.SERVICE_ACCOUNT,
        filename?: string,
        data?: string,
    } | {type: GCPCredentialTypeEnum.DEFAULT},
    credentials_filename?: string,
    regions: string[],
    bucket_name: string,
    vpc: string,
    subnet: string,
}

declare interface IBackendLambda {
    type: 'lambda',
    api_key: string,
    regions: string[],

    storage_backend: {
        type: 'aws',
        bucket_name: string,

        credentials: {
            type: 'access_key',
            access_key: string
            secret_key: string
        }
    }
}

declare interface IBackendLocal {
    type: 'local',
    path: string
}

declare type TBackendConfig = IBackendAWS | IBackendAzure | IBackendGCP | IBackendLambda | IBackendLocal
declare interface IProjectBackend {
    name: string
    config: TBackendConfig
}
