declare type TTemplateParamType = 'name' | 'ide' | 'resources' | 'python_or_docker' | 'repo' | 'working_dir' | 'env';

declare type TTemplateParam = {
    type: TTemplateParamType;
    title?: string;
    name?: string;
    value?: string;
};

declare interface ITemplate {
    type: 'template';
    name: string;
    title: string;
    description?: string;
    parameters: TTemplateParam[];
    configuration: Record<string, unknown>;
}
