export const getProjectRoleByUserName = (
    project: IProject,
    userName: IProjectMember['user']['username'],
): TProjectRole | null => {
    return project.members.find((m) => m.user.username === userName)?.project_role ?? null;
};

export const getMemberCanManageSecrets = (project: IProject, userName: IProjectMember['user']['username']): boolean => {
    const member = project.members.find((m) => m.user.username === userName);
    return member?.permissions?.can_manage_secrets ?? false;
};
