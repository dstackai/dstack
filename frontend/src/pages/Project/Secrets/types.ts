export interface IProps {
    loading?: boolean;
    project?: IProject;
}

export type TFormSecretValue = Partial<IProjectSecret & { serverId: IProjectSecret['id'] }>;
export type TProjectSecretWithIndex = TFormSecretValue & { index: number };
export type TFormValues = { secrets: TFormSecretValue[] };
