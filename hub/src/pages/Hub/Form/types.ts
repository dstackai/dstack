export interface IProps {
    initialValues?: IHub;
    loading?: boolean;
    onCancel: () => void;
    onSubmit: (user: IHub) => void;
}

export type TBackendOption = { label: string; value: THubBackendType; description: string; disabled?: boolean };
