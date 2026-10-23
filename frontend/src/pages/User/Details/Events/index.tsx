import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Button, Container, Header, Loader, SegmentedControl, SpaceBetween } from 'components';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';
import { useGetUserQuery } from 'services/user';

import { EventList } from 'pages/Events/List';
import { getEventsOrderSearchParams } from 'pages/Events/List/hooks/useEventsOrder';

export const Events: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramUserName = params.userName ?? '';
    const navigate = useNavigate();
    const [filterParamName, setFilterParamName] = useState<keyof TEventListFilters>('actors');
    const { data, isLoading } = useGetUserQuery({ name: paramUserName });

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

    const goToEventsPage = (ascending: boolean) => {
        const searchParams = new URLSearchParams({
            [filterParamName]: data?.id ?? '',
            ...getEventsOrderSearchParams(ascending),
        });
        navigate(`${ROUTES.EVENTS.LIST}?${searchParams}`);
    };

    if (isLoading || !data)
        return (
            <Container>
                <Loader />
            </Container>
        );

    return (
        <EventList
            renderHeader={({ ascending }) => {
                return (
                    <Header
                        variant="awsui-h1-sticky"
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
                                <SegmentedControl
                                    selectedId={filterParamName}
                                    onChange={({ detail }) => setFilterParamName(detail.selectedId as keyof TEventListFilters)}
                                    options={[
                                        { text: 'Actor', id: 'actors' },
                                        { text: 'Target user', id: 'target_users' },
                                    ]}
                                />
                                <Button onClick={() => goToEventsPage(ascending)}>{t('common.full_view')}</Button>
                            </SpaceBetween>
                        }
                    />
                );
            }}
            permanentFilters={{ [filterParamName]: [data.id] }}
            showFilters={false}
        />
    );
};
