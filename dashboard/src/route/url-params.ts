export enum URL_PARAMS {
    USER_NAME = 'userName',
    REPO_USER_NAME = 'repoUserName',
    REPO_NAME = 'repoName',
    RUN_NAME = 'runName',
    WORKFLOW_NAME = 'workflowName',
}

export const getPathParamForRouter = (key: keyof typeof URL_PARAMS): string => {
    return ':' + URL_PARAMS[key];
};
