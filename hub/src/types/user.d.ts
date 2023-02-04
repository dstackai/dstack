declare type TPermissionLevel = 'Read' | 'Admin' | 'Run'

declare interface IUser {
    id: number
    user_name: string;
    token: string
    email: string;
    permission_level: TPermissionLevel
}

declare interface IUserAuthData extends Pick<IUser, 'token'>{}

declare interface IUserSmall extends Pick<IUser, 'user_name'>{}

