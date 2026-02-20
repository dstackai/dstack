declare type TTemplateParamType = 'name' | 'ide' | 'resources' | 'python_or_docker' | 'repo' | 'working_dir' | 'env';

declare type TTemplateParam = {
    type: TTemplateParamType;
    title?: string;
    name?: string;
    value?: string;
};

declare interface ITemplate {
    type: 'ui-template';
    id: string;
    title: string;
    parameters: TTemplateParam[];

    template: object;
}
