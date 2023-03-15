declare type THubBackendType = 'aws' | 'gcp' | 'azure';

declare type THubBackend = { type: THubBackendType } & THubBackendAWSWithTitles & THubBackendGCP
declare interface IHub {
    hub_name: string,
    backend: THubBackend,
    members: IHubMember[]
}

declare type TAwsBucket = {
    name: string;
    created?: string;
    region?: string;
}

declare interface IHubAwsBackendValues {
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

declare type IHubBackendValues = { type: THubBackendType } & IHubAwsBackendValues

declare interface THubBackendAWS {
    access_key: string,
    secret_key: string,
    region_name: string,
    s3_bucket_name: string,
    ec2_subnet_id: string | null,
}

declare interface THubBackendGCP {
    project: string,
    region: string,
    zone: string,
    bucket: string,
    vpc: string,
    subnet: string,
    credentials_file: string,
}

declare interface THubBackendAWSWithTitles extends THubBackendAWS {
    region_name_title: string,
}

declare interface IHubMember {
    user_name: string,
    hub_role: THubRole,
}

declare type THubRole = 'read' | 'run' | 'admin'
