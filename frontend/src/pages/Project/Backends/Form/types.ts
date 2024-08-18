export interface IProps {
    initialValues?: TBackendConfig;
    loading?: boolean;
    onCancel: () => void;
    onSubmit: (backend: TBackendConfig) => Promise<TBackendConfig>;
}

export enum BackendTypesEnum {
    AWS = 'aws',
    AZURE = 'azure',
    GCP = 'gcp',
    LAMBDA = 'lambda',
}

export type TBackendOption = { label: string; value: TBackendType; description: string; disabled?: boolean };
