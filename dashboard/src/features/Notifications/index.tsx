import React from 'react';
import cn from 'classnames';
import { useAppDispatch, useAppSelector } from 'hooks';
import Button from 'components/Button';
import { ReactComponent as CloseIcon } from 'assets/icons/close.svg';
import { removeNotification, selectNotifications } from './slice';
import { Notification } from './types';
import css from './index.module.css';

export type Props = React.HTMLAttributes<HTMLDivElement>;

const Notifications: React.FC<Props> = ({ className, ...props }) => {
    const notifications = useAppSelector(selectNotifications);
    const dispatch = useAppDispatch();

    const remove = (uid: Notification['uid']) => {
        dispatch(removeNotification(uid));
    };

    return (
        <div className={cn(css.notifications, className)} {...props}>
            {notifications.map((n) => (
                <div className={cn(css.notification, css[`type-${n.type}`])} key={n.uid}>
                    <div className={css.body}>
                        <span className={css.title}>{n.title}</span> <span className={css.text}>{n.message}</span>
                    </div>

                    <Button
                        className={css.close}
                        displayAsRound
                        appearance="gray-transparent"
                        icon={<CloseIcon />}
                        onClick={() => remove(n.uid)}
                    />
                </div>
            ))}
        </div>
    );
};

export default Notifications;
