export interface IProps {
    initialValues?: IHubMember[];
    loading?: boolean;
    onChange: (user: IHubMember[]) => void;
}

export type THubMemberWithIndex = IHubMember & { index: number };
export type TFormValues = { members: IHubMember[] };
