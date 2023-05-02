enum RepoTypeEnum {
    REMOTE = 'remote',
    LOCAL = 'local',
}

export const getRepoDisplayName = (repo: IRepo): string => {
    let repoName = '';

    if (repo.repo_info.repo_type === RepoTypeEnum.LOCAL) {
        const { repo_dir } = repo.repo_info;
        repoName = repo_dir.replace(/^\//, '');
    }
    if (repo.repo_info.repo_type === RepoTypeEnum.REMOTE) {
        const { repo_user_name, repo_name } = repo.repo_info;
        repoName = `${repo_user_name}/${repo_name}`;
    }

    return repoName;
};
