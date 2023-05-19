export interface IProps extends Partial<Pick<TRequestLogsParams, 'name' | 'repo_id' | 'run_name'>> {
    className?: string;
}

export interface ITableItem {
    name: string;
    path: string;
    type: string;
    size: number | null;
}
