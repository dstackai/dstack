import { useAppSelector, usePermissionGuard } from 'hooks';

import { selectUserData } from 'App/slice';

import { getProjectRoleByUserName } from '../utils';

import { GlobalUserRole } from '../../../types';

export const useCheckAvailableProjectPermission = () => {
    const userData = useAppSelector(selectUserData);
    const userName = userData?.username ?? '';
    const userGlobalRole = userData?.global_role ?? '';
    const [isGlobalAdmin] = usePermissionGuard({ allowedGlobalRoles: [GlobalUserRole.ADMIN] });

    const isAvailableDeletingPermission = (project: IProject) => {
        return getProjectRoleByUserName(project, userName) === 'admin' || userGlobalRole === 'admin';
    };

    const isAvailableAddProjectPermission = (project: IProject) => {
        return getProjectRoleByUserName(project, userName) === 'admin' || userGlobalRole === 'admin';
    };

    const isProjectAdmin = (project: IProject) => {
        return getProjectRoleByUserName(project, userName) === 'admin' || userGlobalRole === 'admin';
    };

    const isEnterpriseAndAdmin = isGlobalAdmin && process.env.UI_VERSION === 'enterprise';

    return { isAvailableDeletingPermission, isAvailableAddProjectPermission, isProjectAdmin, isEnterpriseAndAdmin } as const;
};
