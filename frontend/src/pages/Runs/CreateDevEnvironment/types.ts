export interface IRunEnvironmentFormValues {
    offer: IGpu;
    name: string;
    ide: 'cursor' | 'vscode';
    config_yaml: string;
    docker: boolean;
    image?: string;
    python?: string;
    repo?: string;
    repo_local_path?: string;
}
