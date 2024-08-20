import { useAppSelector, usePermissionGuard } from 'hooks';

import { selectUserData } from 'App/slice';

import { getProjectRoleByUserName } from '../utils';

import { GlobalUserRole } from '../../../types';

export const useCheckAvailableProjectPermission = () => {
    const userData = useAppSelector(selectUserData);
    const userName = userData?.username ?? '';
    const userGlobalRole = userData?.global_role ?? '';
    const [isGlobalAdmin] = usePermissionGuard({ allowedGlobalRoles: [GlobalUserRole.ADMIN] });

    const isAvailableDeletingPermission = (project: IProject): boolean => {
        return getProjectRoleByUserName(project, userName) === 'admin' || userGlobalRole === 'admin';
    };

    const isAvailableAddProjectPermission = (project: IProject): boolean => {
        return getProjectRoleByUserName(project, userName) === 'admin' || userGlobalRole === 'admin';
    };

    const isProjectAdmin = (project: IProject): boolean => {
        return getProjectRoleByUserName(project, userName) === 'admin' || userGlobalRole === 'admin';
    };

    const isProjectManager = (project: IProject): boolean => {
        return isProjectAdmin(project) || getProjectRoleByUserName(project, userName) === 'manager';
    };

    const isAvailableProjectManaging =
        (isGlobalAdmin && process.env.UI_VERSION === 'enterprise') || process.env.UI_VERSION === 'sky';

    return {
        isAvailableDeletingPermission,
        isAvailableAddProjectPermission,
        isProjectAdmin,
        isProjectManager,
        isAvailableProjectManaging,
    } as const;
};
