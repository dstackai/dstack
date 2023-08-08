export interface IProps {
    initialValues?: TBackendConfig;
    loading?: boolean;
    onCancel: () => void;
    onSubmit: (backend: TBackendConfig) => Promise<TBackendConfig>;
}

export enum BackendTypesEnum {
    AWS = 'aws',
    GCP = 'gcp',
    AZURE = 'azure',
    LAMBDA = 'lambda',
    LOCAL = 'local',
}

export type TBackendOption = { label: string; value: TBackendType; description: string; disabled?: boolean };
