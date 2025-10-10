declare interface ILogItem {
    log_source: 'stdout' | 'stderr';
    timestamp: string;
    message: string;
}

declare type TRequestLogsParams = {
    project_name: IProject['project_name'];
    run_name: IRun['run_name'];
    job_submission_id: string;
    start_time?: DateTime;
    end_time?: DateTime;
    descending?: boolean;
    limit?: number;
    diagnose?: boolean;
    next_token?: string;
};

declare type TResponseLogsParams = {
    logs: ILogItem[];
    external_url?: string;
    next_token?: string;
};
