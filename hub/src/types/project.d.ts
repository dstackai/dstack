
declare type TProjectBackend = { type: TBackendType } & IBackendAWSWithTitles & IBackendAzure & IBackendGCP & IBackendLambda & IBackendLocal
declare interface IProject {
    project_name: string,
    members: IProjectMember[]
}

declare interface IProjectMember {
    user_name: string,
    project_role: TProjectRole,
}

declare type TProjectRole = 'read' | 'run' | 'admin'
