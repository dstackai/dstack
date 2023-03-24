export interface IProps {
    initialValues?: IProject;
    loading?: boolean;
    onCancel: () => void;
    onSubmit: (user: IProject) => Promise<IProject>;
}

export type TBackendOption = { label: string; value: TProjectBackendType; description: string; disabled?: boolean };
