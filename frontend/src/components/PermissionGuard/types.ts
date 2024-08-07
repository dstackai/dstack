import React from 'react';

import { GlobalUserRole, ProjectUserRole } from 'types';

export interface IProps {
    allowedGlobalRoles?: GlobalUserRole[];
    allowedProjectRoles?: ProjectUserRole[];
    projectRole?: string;
    children: React.ReactNode;
}
