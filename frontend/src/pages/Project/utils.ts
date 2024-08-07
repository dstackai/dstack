export const getProjectRoleByUserName = (
    project: IProject,
    userName: IProjectMember['user']['username'],
): TProjectRole | null => {
    return project.members.find((m) => m.user.username === userName)?.project_role ?? null;
};
