import { useMemo } from 'react';

import { selectUserData } from 'App/slice';

import useAppSelector from './useAppSelector';

import { GlobalUserRole, ProjectUserRole } from '../types';

interface Args {
    allowedGlobalRoles?: GlobalUserRole[];
    allowedProjectRoles?: ProjectUserRole[];
    projectRole?: string;
}
export const usePermissionGuard = ({ allowedGlobalRoles, allowedProjectRoles, projectRole }: Args) => {
    const userData = useAppSelector(selectUserData);
    const userGlobalRole = userData?.global_role ?? '';

    const isAvailableForGlobalUser = useMemo(() => {
        if (!allowedGlobalRoles?.length) return false;

        return allowedGlobalRoles.includes(userGlobalRole as GlobalUserRole);
    }, [allowedGlobalRoles, userGlobalRole]);

    const isAvailableForProjectUser = useMemo(() => {
        if (!allowedProjectRoles?.length) return false;

        return allowedProjectRoles.includes(projectRole as ProjectUserRole);
    }, [allowedGlobalRoles, userGlobalRole]);

    const isAvailableContent = isAvailableForGlobalUser || isAvailableForProjectUser;

    return [isAvailableContent] as const;
};
