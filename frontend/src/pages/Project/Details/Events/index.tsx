import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Button, Header, SpaceBetween } from 'components';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';

import { EventList } from 'pages/Events/List';

export const Events: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const navigate = useNavigate();

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.FORMAT(paramProjectName),
        },
        {
            text: t('projects.events'),
            href: ROUTES.PROJECT.DETAILS.EVENTS.FORMAT(paramProjectName),
        },
    ]);

    const goToEventsPage = () => {
        navigate(ROUTES.EVENTS.LIST + `?within_projects=${paramProjectName}`);
    };

    return (
        <EventList
            renderHeader={() => {
                return (
                    <Header
                        variant="awsui-h1-sticky"
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
                                <Button onClick={goToEventsPage}>{t('common.full_view')}</Button>
                            </SpaceBetween>
                        }
                    />
                );
            }}
            permanentFilters={{ within_projects: [paramProjectName] }}
            showFilters={false}
        />
    );
};
