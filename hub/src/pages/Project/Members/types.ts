export interface IProps {
    initialValues?: IProjectMember[];
    loading?: boolean;
    onChange: (user: IProjectMember[]) => void;
    readonly?: boolean;
}

export type TProjectMemberWithIndex = IProjectMember & { index: number };
export type TFormValues = { members: IProjectMember[] };
