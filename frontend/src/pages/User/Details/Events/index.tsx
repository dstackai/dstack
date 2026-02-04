import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Button, Header, SegmentedControl, SpaceBetween } from 'components';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';

import { EventList } from 'pages/Events/List';

export const Events: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramUserName = params.userName ?? '';
    const navigate = useNavigate();
    const [filterParamName, setFilterParamName] = useState<keyof TEventListFilters>('target_users');

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

    const goToEventsPage = () => {
        navigate(ROUTES.EVENTS.LIST + `?${filterParamName}=${paramUserName}`);
    };

    return (
        <EventList
            renderHeader={() => {
                return (
                    <Header
                        variant="awsui-h1-sticky"
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
                                <SegmentedControl
                                    selectedId={filterParamName}
                                    onChange={({ detail }) => setFilterParamName(detail.selectedId as keyof TEventListFilters)}
                                    options={[
                                        { text: 'Target user', id: 'target_users' },
                                        { text: 'Actor', id: 'actors' },
                                    ]}
                                />
                                <Button onClick={goToEventsPage}>{t('common.full_view')}</Button>
                            </SpaceBetween>
                        }
                    />
                );
            }}
            permanentFilters={{ [filterParamName]: [paramUserName] }}
            showFilters={false}
        />
    );
};
