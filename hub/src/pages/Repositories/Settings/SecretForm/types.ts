export type FormValues = Required<ISecret>;

export interface IProps {
    onClose?: () => void;
    initialValues?: Partial<FormValues>;
    projectName: IProject['project_name'];
    repoId: IRepo['repo_id'];
}
