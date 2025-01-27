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
    USER = 'user',
    MANAGER = 'manager'
}

export enum UserPermission {
    CAN_CREATE_PROJECTS = 'CAN_CREATE_PROJECTS',
}

export const userPermissionMap: Record<TUserPermissionKeys, UserPermission> = {
    'can_create_projects': UserPermission.CAN_CREATE_PROJECTS
}
