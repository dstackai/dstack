export interface IProps {
    initialValues?: IProject;
    loading?: boolean;
    onCancel: () => void;
    onSubmit: (user: IProject) => Promise<IProject>;
}

export enum BackendTypesEnum {
    AWS = 'aws',
    GCP = 'gcp',
    AZURE = 'azure',
    LAMBDA = 'lambda',
    LOCAL = 'local',
}

export type TBackendOption = { label: string; value: TProjectBackendType; description: string; disabled?: boolean };
