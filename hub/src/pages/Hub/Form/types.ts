export interface IProps {
    initialValues?: IHub;
    loading?: boolean;
    onCancel: () => void;
    onSubmit: (user: IHub) => void;
}

export type TBackendSelectOption = { label: string; value: THubBackendType };
