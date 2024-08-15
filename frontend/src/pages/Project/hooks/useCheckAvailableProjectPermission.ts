import { useAppSelector, usePermissionGuard } from 'hooks';
import { UserPermission } from 'types';

import { selectUserData } from 'App/slice';

import { getProjectRoleByUserName } from '../utils';

export const useCheckAvailableProjectPermission = () => {
    const userData = useAppSelector(selectUserData);
    const userName = userData?.username ?? '';
    const userGlobalRole = userData?.global_role ?? '';
    const [hasPermissionForProjectManaging] = usePermissionGuard({
        allowedPermissions: [UserPermission.DSTACK_USER_CAN_CREATE_PROJECTS],
    });

    const isAvailableDeletingPermission = (project: IProject) => {
        return getProjectRoleByUserName(project, userName) === 'admin' || userGlobalRole === 'admin';
    };

    const isAvailableAddProjectPermission = (project: IProject) => {
        return getProjectRoleByUserName(project, userName) === 'admin' || userGlobalRole === 'admin';
    };

    const isProjectAdmin = (project: IProject) => {
        return getProjectRoleByUserName(project, userName) === 'admin' || userGlobalRole === 'admin';
    };

    const isAvailableProjectManaging = hasPermissionForProjectManaging;

    return {
        isAvailableDeletingPermission,
        isAvailableAddProjectPermission,
        isProjectAdmin,
        isAvailableProjectManaging,
    } as const;
};
