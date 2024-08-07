export interface IProps extends Partial<Pick<TRequestLogsParams, 'project_name' | 'run_name'>> {
    className?: string;
}

export interface ITableItem {
    name: string;
    path: string;
    type: string;
    size: number | null;
}
