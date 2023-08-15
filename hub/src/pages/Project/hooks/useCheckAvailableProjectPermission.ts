import { useAppSelector } from 'hooks';

import { selectUserData } from 'App/slice';

import { getProjectRoleByUserName } from '../utils';

export const useCheckAvailableProjectPermission = () => {
    const userData = useAppSelector(selectUserData);
    const userName = userData?.user_name ?? '';
    const userGlobalRole = userData?.global_role ?? '';
    const isAvailableDeletingPermission = (project: IProject) => {
        return getProjectRoleByUserName(project, userName) === 'admin' || userGlobalRole === 'admin';
    };

    return { isAvailableDeletingPermission } as const;
};
