import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { Link, NavigateLink } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { ROUTES } from 'routes';

export const useColumnDefinitions = () => {
    const { t } = useTranslation();

    return useMemo(() => {
        return [
            {
                id: 'name',
                header: t('users.user_name'),
                cell: (item: IUser) => (
                    <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(item.username)}>{item.username}</NavigateLink>
                ),
            },
            {
                id: 'email',
                header: t('users.email'),
                cell: (item: IUser) => (item.email ? <Link href={`mailto:${item.email}`}>{item.email}</Link> : '-'),
            },
            {
                id: 'global_role',
                header: t('users.global_role'),
                cell: (item: IUser) => t(`roles.${item.global_role}`),
            },
            process.env.UI_VERSION === 'sky' && {
                id: 'created_at',
                header: t('users.created_at'),
                cell: (item: IUser) => format(new Date(item.created_at), DATE_TIME_FORMAT),
            },
        ].filter(Boolean);
    }, []);
};
