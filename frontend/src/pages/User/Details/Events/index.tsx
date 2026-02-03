import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';

import { EventList } from 'pages/Events/List';

export const Events: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramUserName = params.userName ?? '';

    useBreadcrumbs([
        {
            text: t('navigation.account'),
            href: ROUTES.USER.LIST,
        },
        {
            text: paramUserName,
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
        {
            text: t('users.events'),
            href: ROUTES.USER.EVENTS.FORMAT(paramUserName),
        },
    ]);

    return <EventList variant="borderless" permanentFilters={{ target_users: [paramUserName] }} />;
};
