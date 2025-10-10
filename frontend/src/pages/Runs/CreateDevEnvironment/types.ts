export interface IRunEnvironmentFormValues {
    offer: IGpu;
    name: string;
    ide: 'cursor' | 'vscode';
    config_yaml: string;
}
