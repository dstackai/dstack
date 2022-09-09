import { removeAllNotifications, removeNotification, addNotification } from 'features/Notifications/slice';
import { Notification } from 'features/Notifications/types';
import useAppDispatch from './useAppDispatch';

function useNotifications() {
    const dispatch = useAppDispatch();

    const push = (notification: Omit<Notification, 'uid'>) => {
        dispatch(addNotification(notification));
    };

    const remove = (uid: Notification['uid']) => {
        dispatch(removeNotification(uid));
    };

    const removeAll = () => {
        dispatch(removeAllNotifications());
    };

    return {
        push,
        remove,
        removeAll,
    };
}

export default useNotifications;
