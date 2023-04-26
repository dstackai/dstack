declare type TRepoType  = 'remote'

declare interface IRepo {
    repo_type: TRepoType,
    repo_id: string,
    last_run_at: number,
    tags_count: number,
    repo_info : {
        repo_host_name: string,
        repo_port: number | null,
        repo_user_name: string,
        repo_name: string
    }
}
