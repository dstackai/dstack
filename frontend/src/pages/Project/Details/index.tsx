import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useMatch, useParams } from 'react-router-dom';

import { ContentLayout, DetailsHeader, Tabs } from 'components';

import { ROUTES } from 'routes';

import styles from './styles.module.scss';

export const ProjectDetails: React.FC = () => {
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const { t } = useTranslation();

    const matchSettings = useMatch(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    const matchEvents = useMatch(ROUTES.PROJECT.DETAILS.EVENTS.FORMAT(paramProjectName));

    const tabs: {
        label: string;
        id: string;
        href: string;
    }[] = [
        {
            label: t('projects.settings'),
            id: 'settings',
            href: ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName),
        },
        {
            label: t('projects.events'),
            id: 'events',
            href: ROUTES.PROJECT.DETAILS.EVENTS.FORMAT(paramProjectName),
        },
    ].filter(Boolean);

    const showTabs = useMemo<boolean>(() => {
        return Boolean(matchSettings) || Boolean(matchEvents);
    }, [matchSettings, matchEvents]);

    return (
        <div className={styles.page}>
            <ContentLayout header={<DetailsHeader title={paramProjectName} />}>
                {showTabs && <Tabs withNavigation tabs={tabs} />}

                <Outlet />
            </ContentLayout>
        </div>
    );
};
