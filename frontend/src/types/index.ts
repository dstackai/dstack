export enum AWSCredentialTypeEnum {
    DEFAULT = 'default',
    ACCESS_KEY = 'access_key'
}

export enum AzureCredentialTypeEnum {
    DEFAULT = 'default',
    CLIENT = 'client'
}

export enum GCPCredentialTypeEnum {
    DEFAULT = 'default',
    SERVICE_ACCOUNT = 'service_account'
}

export enum GlobalUserRole {
    ADMIN = 'admin',
    USER = 'user'
}

export enum ProjectUserRole {
    ADMIN = 'admin',
    USER = 'user'
}

export enum UserPermission {
    DSTACK_USER_CAN_CREATE_PROJECTS = 'DSTACK_USER_CAN_CREATE_PROJECTS',
    DSTACK_USER_CAN_CREATE_GATEWAYS = 'DSTACK_USER_CAN_CREATE_GATEWAYS',
    DSTACK_USER_CAN_CREATE_ON_PREM_FLEETS = 'DSTACK_USER_CAN_CREATE_ON_PREM_FLEETS'
}


