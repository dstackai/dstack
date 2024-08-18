import React from 'react';
import Flashbar from '@cloudscape-design/components/flashbar';

import { useAppSelector } from 'hooks';

import { selectNotifications } from './slice';

export const Notifications: React.FC = () => {
    const notifications = useAppSelector(selectNotifications);

    return <Flashbar items={notifications} />;
};
