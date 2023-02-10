export const getHubRoleByUserName = (hub: IHub, userName: IHubMember['user_name']): THubRole | null => {
    return hub.members.find((m) => m.user_name === userName)?.hub_role ?? null;
};
