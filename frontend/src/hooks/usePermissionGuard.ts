import { useMemo } from 'react';

import { selectUserData } from 'App/slice';

import useAppSelector from './useAppSelector';

import { GlobalUserRole, ProjectUserRole, UserPermission } from '../types';

interface Args {
    allowedGlobalRoles?: GlobalUserRole[];
    allowedProjectRoles?: ProjectUserRole[];
    allowedPermissions?: UserPermission[];
    projectRole?: string;
}
export const usePermissionGuard = ({ allowedGlobalRoles, allowedProjectRoles, allowedPermissions, projectRole }: Args) => {
    const userData = useAppSelector(selectUserData);
    const userGlobalRole = userData?.global_role ?? '';
    const userPermissions = userData?.permissions ?? [];

    const isAvailableForGlobalUser = useMemo(() => {
        if (!allowedGlobalRoles?.length) return false;

        return allowedGlobalRoles.includes(userGlobalRole as GlobalUserRole);
    }, [allowedGlobalRoles, userGlobalRole]);

    const isAvailableForProjectUser = useMemo(() => {
        if (!allowedProjectRoles?.length) return false;

        return allowedProjectRoles.includes(projectRole as ProjectUserRole);
    }, [allowedGlobalRoles, userGlobalRole]);

    const hasPermission = useMemo(() => {
        if (!allowedPermissions?.length) return false;

        return userPermissions.some((userPermission) => allowedPermissions.includes(userPermission as UserPermission));
    }, [allowedGlobalRoles, userGlobalRole]);

    const isAvailableContent = isAvailableForGlobalUser || isAvailableForProjectUser || hasPermission;

    return [isAvailableContent] as const;
};
