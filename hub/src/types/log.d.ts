declare interface ILogItem {
    event_id: string,
    timestamp: string,
    job_id: string,
    log_message: string,
    log_source: string
}

declare type TRequestLogsParams = {
    name: IProject['project_name'],
    repo_id: IRepo['repo_id'],
    run_name: IRun['run_name'],
    start_time?: DateTime,
    end_time?: DateTime,
    descending?: boolean,
    prev_event_id?: string,
    limit?: number
}
