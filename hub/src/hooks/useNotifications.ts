import useAppDispatch from './useAppDispatch';
import { Notification } from 'components/Notifications/types';
import { push, remove } from 'components/Notifications/slice';
import { getUid } from 'libs';

const NOTIFICATION_LIFE_TIME = 6000;

export const useNotifications = () => {
    const dispatch = useAppDispatch();

    const removeNotification = (id: Notification['id']) => {
        dispatch(remove(id));
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

        setTimeout(() => {
            removeNotification(id);
        }, NOTIFICATION_LIFE_TIME);
    };

    return [pushNotification];
};
