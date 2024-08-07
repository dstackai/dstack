export interface IProps {
    members?: IProjectMember[];
    loading?: boolean;
    onChange: (users: IProjectMember[]) => void;
    readonly?: boolean;
}

export type TProjectMemberWithIndex = IProjectMember & { index: number };
export type TFormValues = { members: IProjectMember[] };
