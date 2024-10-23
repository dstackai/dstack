
declare type TProjectBackend = {
    name: string,
    config: IBackendAWS | IBackendAzure | IBackendGCP | IBackendLambda | IBackendLocal | IBackendDstack
}
declare interface IProject {
    project_name: string,
    members: IProjectMember[],
    backends: TProjectBackend[]
    owner: IUser | {username: string},
    created_at: string
}

declare interface IProjectMember {
    project_role: TProjectRole,
    user: IUser | {username: string}
}

declare type TSetProjectMembersParams = {
    project_name: string,
    members: Array<{
        project_role: TProjectRole,
        username: string
    }>
}

declare type TProjectRole = TUserRole | 'manager'
