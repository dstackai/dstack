declare interface IAWSConfig {
    aws_access_key_id: string;
    aws_secret_access_key: string;
    aws_region: string;
    artifacts_s3_bucket: string;
}

declare interface IUser {
    user_name: string;
    github_user_name?: string;
    token: string;
    email: string;
    verified: boolean;
    on_demand_limits_configured: boolean;
    default_configuration: IAWSConfig;
    user_configuration?: IAWSConfig;
}

declare interface ILoginRequestParams {
    user_name: string,
    password: string,
}

declare interface ILoginRequestResponse{
    session: string,
    verified: boolean,
    token: string
}

declare interface ISignUpRequestParams {
    user_name: string;
    email: string;
    password: string;
}

declare interface ISignUpRequestResponse {
    session: string
    token: string
    verified: boolean
}
