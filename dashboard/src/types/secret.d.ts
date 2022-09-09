
declare type TSecretName = string;
declare type TSecretValue = string;

declare interface ISecret {
    secret_id: string,
    secret_name: TSecretName,
    secret_value: TSecretValue,
}
