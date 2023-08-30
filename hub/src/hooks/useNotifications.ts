import { useEffect, useRef } from 'react';

import { push, remove } from 'components/Notifications/slice';
import { Notification } from 'components/Notifications/types';

import { getUid } from 'libs';

import useAppDispatch from './useAppDispatch';

const NOTIFICATION_LIFE_TIME = 6000;

type TUseNotificationsArgs = { temporary?: boolean; liveTime?: number } | undefined;

const defaultArgs: NonNullable<Required<TUseNotificationsArgs>> = { temporary: true, liveTime: NOTIFICATION_LIFE_TIME };
export const useNotifications = (args: TUseNotificationsArgs = defaultArgs) => {
    const dispatch = useAppDispatch();
    const notificationIdsSet = useRef(new Set<ReturnType<typeof getUid>>());

    const { temporary, liveTime } = {
        ...defaultArgs,
        ...args,
    };

    const removeNotification = (id: NonNullable<Notification['id']>) => {
        dispatch(remove(id));

        if (notificationIdsSet.current.has(id)) {
            notificationIdsSet.current.delete(id);
        }
    };

    const pushNotification = (notification: Omit<Notification, 'id' | 'dismissible' | 'onDismiss'>) => {
        const id = getUid();

        dispatch(
            push({
                id,
                ...notification,
                dismissible: true,
                onDismiss: () => {
                    removeNotification(id);
                },
            }),
        );

        if (temporary) {
            setTimeout(() => {
                removeNotification(id);
            }, liveTime);
        } else {
            notificationIdsSet.current.add(id);
        }
    };

    useEffect(() => {
        return () => {
            notificationIdsSet.current.forEach((notificationId) => {
                removeNotification(notificationId);
            });
        };
    }, []);

    return [pushNotification];
};
