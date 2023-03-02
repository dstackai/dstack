declare type TUserRole = 'read' | 'admin' | 'run'

declare interface IUser {
    user_name: string;
    token: string
    global_role: TUserRole
}

declare interface IUserAuthData extends Pick<IUser, 'token'>{}

declare interface IUserSmall extends Pick<IUser, 'user_name'>{}

