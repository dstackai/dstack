declare type TProjectBackendType = 'aws' | 'gcp' | 'azure' | 'lambda' | 'local';

declare type TProjectBackend = { type: TProjectBackendType } & TProjectBackendAWSWithTitles & TProjectBackendAzure & TProjectBackendGCP & TProjectBackendLambda & TProjectBackendLocal
declare interface IProject {
    project_name: string,
    backend: TProjectBackend,
    members: IProjectMember[]
}

declare type TAwsBucket = {
    name: string;
    created?: string;
    region?: string;
}

declare interface IProjectAwsBackendValues {
        default_credentials: boolean
        region_name: {
            selected?: string,
            values: { value: string, label: string}[]
        } | null,
        s3_bucket_name: {
            selected?: string,
            values: TAwsBucket[]
        } | null,
        ec2_subnet_id: {
            selected?: string | null,
            values: { value: string, label: string}[]
        } | null,
        extra_regions: {
            selected?: string[] | null,
            values: { value: string, label: string}[]
        } | null,
}

declare interface IProjectAzureBackendValues {
    tenant_id: {
        selected?: string,
        values: { value: string, label: string}[]
    } | null,
    subscription_id: {
        selected?: string,
        values: { value: string, label: string}[]
    } | null,
    location: {
        selected?: string,
        values: { value: string, label: string}[]
    } | null,
    storage_account: {
        selected?: string | null,
        values: { value: string, label: string}[]
    } | null,
}

declare interface TVPCSubnetValue { label: string, vpc: string, subnet: string}

declare interface IProjectGCPBackendValues {
    area: null | {
        selected?: string,
        values: { value: string, label: string}[]
    },
    bucket_name: null | {
        selected?: string,
        values: { value: string, label: string}[]
    },
    region: null | {
        selected?: string,
        values: { value: string, label: string}[]
    },
    vpc_subnet: null | {
        selected?: string,
        values: TVPCSubnetValue[]
    },
    zone: null | {
        selected?: string,
        values: { value: string, label: string}[]
    },
}

declare interface IProjectLambdaBackendValues {
    regions: null | {
        selected?: string,
        values: { value: string, label: string}[]
    },

    storage_backend_type: null | {
        selected?: string,
        values: { value: string, label: string}[]
    },

    storage_backend_values:  null | {
        bucket_name: null | {
            selected?: string,
            values: { value: string, label: string}[]
        }
    },
}

declare type TProjectBackendValuesResponse = IProjectAwsBackendValues & IProjectAzureBackendValues & IProjectGCPBackendValues & IProjectLambdaBackendValues

enum AWSCredentialTypeEnum {
    DEFAULT = 'default',
    ACCESS_KEY = 'access_key'
}
declare interface TProjectBackendAWS {
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

declare interface TProjectBackendAzure {
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

declare interface TProjectBackendGCP {
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

declare interface TProjectBackendLambda {
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

declare interface TProjectBackendLocal {
    path: string
}

declare interface TProjectBackendAWSWithTitles extends TProjectBackendAWS {
    region_name_title: string,
}

declare interface IProjectMember {
    user_name: string,
    project_role: TProjectRole,
}

declare type TProjectRole = 'read' | 'run' | 'admin'
