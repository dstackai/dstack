export interface IRunEnvironmentFormValues {
    project: IProject['project_name'];
    template: string;
    offer: IGpu;
    name: string;
    ide: 'cursor' | 'vscode' | 'windsurf' | 'coder';
    config_yaml: string;
    docker: boolean;
    image?: string;
    python?: string;
    repo_enabled?: boolean;
    repo_url?: string;
    repo_path?: string;
    working_dir?: string;
    password?: string;
}

export type IRunEnvironmentFormKeys = keyof Required<IRunEnvironmentFormValues>;
