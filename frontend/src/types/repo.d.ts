enum RepoTypeEnum {
    REMOTE = 'remote',
    LOCAL = 'local',
}

declare interface IRemoteRunRepoData {
    repo_type: 'remote'
    repo_name: string
    repo_branch?: string
    repo_hash?: string
    repo_diff?: string
    repo_config_name?: string
    repo_config_email?: string
}

declare interface ILocalRunRepoData {
    repo_type: 'local'
    repo_dir: string
}

declare interface VirtualRunRepoData {
    repo_type: 'virtual'
}

declare interface IRepo {
    repo_id: string,
    repo_info: IRemoteRunRepoData | ILocalRunRepoData | VirtualRunRepoData
}
