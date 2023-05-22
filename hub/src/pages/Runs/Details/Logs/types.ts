export interface IProps extends Partial<Pick<TRequestLogsParams, 'name' | 'repo_id' | 'run_name'>> {
    className?: string;
}
