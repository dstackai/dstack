declare interface IRepository {
    user_name: string,
    repo_user_name: string,
    repo_name: string,
    repo_url: string,
    visibility: 'private' | 'public',
    last_run_at: number,
    tags_count: number,
}
