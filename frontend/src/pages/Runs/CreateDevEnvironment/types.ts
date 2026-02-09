export interface IRunEnvironmentFormValues {
    offer: IGpu;
    env_type?: 'web' | 'desktop';
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
