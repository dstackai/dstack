export interface IProps {
    initialValues?: IProjectMember[];
    loading?: boolean;
    onChange: (user: IProjectMember[]) => void;
}

export type TProjectMemberWithIndex = IProjectMember & { index: number };
export type TFormValues = { members: IProjectMember[] };
