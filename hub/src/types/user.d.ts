declare interface IUser {
    user_name: string;
    token: string;
    email: string;
}

declare interface IUserSmall extends Pick<IUser, 'token' | 'user_name'>{}

declare type TTokenError = {
    error_code: 'invalid_token' | 'undefined_token'
}
