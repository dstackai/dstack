export interface IProps {
    initialValues?: Partial<IProject>;
    loading?: boolean;
    onCancel: () => void;
    onSubmit: (user: IProject) => Promise<IProject>;
}
