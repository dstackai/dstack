declare interface IUser {
    user_name: string;
    email: string;
}

declare interface IUserAuthData {
    token: string
}

declare interface IUserSmall extends Pick<IUser, 'user_name'>{}

