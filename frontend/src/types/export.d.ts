declare interface IExportImport {
    project_name: IProject['project_name'];
}

declare interface IExportedModel {
    name: string;
}

declare interface IExport {
    name: string;
    imports: IExportImport[];
    exported_models: IExportedModel[];
}
