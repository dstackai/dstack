declare type TProjectBackendType = 'aws' | 'gcp' | 'azure' | 'local';

declare type TProjectBackend = { type: TProjectBackendType } & TProjectBackendAWSWithTitles & TProjectBackendAzure & TProjectBackendGCP & TProjectBackendLocal
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
        region_name: {
            selected?: string,
            values: { value: string, label: string}[]
        },
        s3_bucket_name: {
            selected?: string,
            values: TAwsBucket[]
        },
        ec2_subnet_id: {
            selected?: string | null,
            values: { value: string, label: string}[]
        },
}

declare interface IProjectAzureBackendValues {
    subscription_id: {
        selected?: string,
        values: { value: string, label: string}[]
    },
    location: {
        selected?: string,
        values: { value: string, label: string}[]
    },
    storage_account: {
        selected?: string | null,
        values: { value: string, label: string}[]
    },
}

declare interface TVPCSubnetValue { label: string, vpc: string, subnet: string}

declare interface IProjectGCPBackendValues {
    area: {
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

declare type TProjectBackendValuesResponse = IProjectAwsBackendValues & IProjectAzureBackendValues & IProjectGCPBackendValues

declare interface TProjectBackendAWS {
    access_key: string,
    secret_key: string,
    region_name: string,
    s3_bucket_name: string,
    ec2_subnet_id: string | null,
}

declare interface TProjectBackendAzure {
    tenant_id: string,
    client_id?: string,
    client_secret?: string,
    subscription_id: string,
    location: string,
    storage_account: string,
}

declare interface TProjectBackendGCP {
    credentials?: string,
    credentials_filename?: string,
    area: string,
    region: string,
    zone: string,
    bucket_name: string,
    vpc: string,
    subnet: string,
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
