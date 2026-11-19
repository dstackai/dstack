declare interface IImportExportedModel {
    name: string;
    // The importer project's URL for the model. Empty while no service serves the model
    base_url: string | null;
}

declare interface IImportExport {
    name: string;
    // The project that exports
    project_name: IProject['project_name'];
    exported_models: IImportExportedModel[];
}

declare interface IImport {
    export: IImportExport;
}

declare type TProjectImports = {
    project_name: IProject['project_name'];
    imports: IImport[];
};
