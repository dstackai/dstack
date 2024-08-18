import React from 'react';

import { usePermissionGuard } from 'hooks';

import { IProps } from './types';

export const PermissionGuard: React.FC<IProps> = ({ children, ...props }) => {
    const [isAvailable] = usePermissionGuard(props);

    if (!isAvailable) return null;

    return <>{children}</>;
};
