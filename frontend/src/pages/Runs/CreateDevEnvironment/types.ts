export interface IRunEnvironmentFormValues {
    offer: IGpu;
    name: string;
    ide: 'cursor' | 'vscode';
    config_yaml: string;
    docker: boolean;
    image?: string;
    python?: string;
    repo_enabled?: boolean;
    repo_url?: string;
    repo_path?: string;
    working_dir?: string;
}

export type IRunEnvironmentFormKeys = keyof Required<IRunEnvironmentFormValues>;
