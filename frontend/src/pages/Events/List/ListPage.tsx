import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Header, SpaceBetween } from 'components';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';

import { EventList } from './index';

export const ListPage: React.FC = () => {
    const { t } = useTranslation();

    useBreadcrumbs([
        {
            text: t('navigation.events'),
            href: ROUTES.EVENTS.LIST,
        },
    ]);

    return (
        <EventList
            variant="full-page"
            withSearchParams
            renderHeader={({ refreshAction, disabledRefresh }) => {
                return (
                    <Header
                        variant="awsui-h1-sticky"
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
                                <Button
                                    iconName="refresh"
                                    disabled={disabledRefresh}
                                    ariaLabel={t('common.refresh')}
                                    onClick={refreshAction}
                                />
                            </SpaceBetween>
                        }
                    >
                        {t('navigation.events')}
                    </Header>
                );
            }}
        />
    );
};
