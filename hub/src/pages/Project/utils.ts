export const getProjectRoleByUserName = (project: IProject, userName: IProjectMember['user_name']): TProjectRole | null => {
    return project.members.find((m) => m.user_name === userName)?.project_role ?? null;
};

export const getLambdaStorageTypeLabel = (type: IBackendLambda['storage_backend']['type']) => {
    return { aws: 'AWS S3' }[type];
};
