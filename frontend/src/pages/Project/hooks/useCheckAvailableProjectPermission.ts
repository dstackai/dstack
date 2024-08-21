import { useAppSelector, usePermissionGuard } from 'hooks';
import { UserPermission } from 'types';

import { selectUserData } from 'App/slice';

import { getProjectRoleByUserName } from '../utils';

export const useCheckAvailableProjectPermission = () => {
    const userData = useAppSelector(selectUserData);
    const userName = userData?.username ?? '';
    const userGlobalRole = userData?.global_role ?? '';

    const [hasPermissionForProjectManaging] = usePermissionGuard({
        allowedPermissions: [UserPermission.CAN_CREATE_PROJECTS],
    });

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

    const isAvailableProjectManaging = hasPermissionForProjectManaging;

    return {
        isAvailableDeletingPermission,
        isAvailableAddProjectPermission,
        isProjectAdmin,
        isProjectManager,
        isAvailableProjectManaging,
    } as const;
};
