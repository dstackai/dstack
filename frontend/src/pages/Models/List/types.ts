export interface IModelExtended extends IModel {
    run_name: string;
    project_name: string;
    submitted_at: string;
    user: string;
    resources: string | null;
    price: number | null;
    region: string | null;
    repository: string | null;
    backend: TBackendType | null;
}
