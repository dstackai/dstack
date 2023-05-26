declare interface ISecret {
    secret_name: string;
    secret_value?: string;
}

declare type TGetSecretsRequestParams = {
    project_name: IProject['project_name'];
    repo_id: IRepo['repo_id'];
};

declare type TAddSecretRequestParams = {
    project_name: IProject['project_name'];
    repo_id: IRepo['repo_id'];
    secret: Required<ISecret>;
};

declare type TDeleteSecretRequestParams = {
    project_name: IProject['project_name'];
    repo_id: IRepo['repo_id'];
    secret_name: ISecret['secret_name'];
};
