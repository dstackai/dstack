declare type TBackendType = 'aws' | 'gcp' | 'azure' | 'lambda' | 'local';

type TBackendValueField<TValuesType = { value: string, label: string}[]> = {
    selected?: string,
    values: TValuesType
} | null;


declare interface IAwsBackendValues {
    default_credentials: boolean
    region_name: TBackendValueField,
    s3_bucket_name: TBackendValueField<TAwsBucket[]>,
    ec2_subnet_id: TBackendValueField,
    extra_regions: TBackendValueField,
}

declare interface IAzureBackendValues {
    tenant_id: TBackendValueField,
    subscription_id: TBackendValueField,
    location: TBackendValueField,
    storage_account: TBackendValueField,
}

declare interface TVPCSubnetValue { label: string, vpc: string, subnet: string}

declare interface IGCPBackendValues {
    area: TBackendValueField,
    bucket_name: TBackendValueField,
    region: TBackendValueField,
    vpc_subnet: TBackendValueField<TVPCSubnetValue[]>
    zone: TBackendValueField,
}

declare interface ILambdaBackendValues {
    regions: TBackendValueField,
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
    region_name: string,
    s3_bucket_name: string,
    ec2_subnet_id: string | null,
    extra_regions: string[],
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
    location: string,
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
    area: string,
    region: string,
    zone: string,
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

declare interface IBackendAWSWithTitles extends IBackendAWS {
    region_name_title: string,
}

declare type TBackendConfig = IBackendAWS | IBackendAzure | IBackendGCP | IBackendLambda | IBackendLocal
declare interface IBackend {
    name: string
    config: TBackendConfig
}
