declare type TTemplateParam = {
    type: string;
    title?: string;
    name?: string;
    value?: string;
};

declare interface ITemplate {
    type: 'ui-template';
    id: string;
    title: string;
    params: TTemplateParam[];

    template: object;
}
