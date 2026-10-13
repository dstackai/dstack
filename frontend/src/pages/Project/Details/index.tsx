import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useMatch, useParams } from 'react-router-dom';
import { product } from 'product';

import { ContentLayout, DetailsHeader, Tabs } from 'components';

import { ROUTES } from 'routes';
import { projectApi } from 'services/project';

import { useCheckAvailableProjectPermission } from '../hooks/useCheckAvailableProjectPermission';

import styles from './styles.module.scss';

export const ProjectDetails: React.FC = () => {
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const { t } = useTranslation();

    const matchSettings = useMatch(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    const matchQuotas = useMatch(ROUTES.PROJECT.DETAILS.QUOTAS.FORMAT(paramProjectName));
    const matchEvents = useMatch(ROUTES.PROJECT.DETAILS.EVENTS.FORMAT(paramProjectName));
    const { currentData: project } = projectApi.endpoints.getProject.useQueryState({ name: paramProjectName });
    const { isProjectAdmin } = useCheckAvailableProjectPermission();
    const showTabs = useMemo<boolean>(() => {
        return Boolean(matchSettings) || Boolean(matchQuotas) || Boolean(matchEvents);
    }, [matchSettings, matchQuotas, matchEvents]);
    // TODO: Gate Quotas on dstack backend presence once the project response exposes it.
    const hasQuotas = product.hasBilling && project && isProjectAdmin(project);

    const tabs = [
        {
            label: t('projects.settings'),
            id: 'settings',
            href: ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName),
        },
        product.hasEvents && {
            label: t('projects.events'),
            id: 'events',
            href: ROUTES.PROJECT.DETAILS.EVENTS.FORMAT(paramProjectName),
        },
        hasQuotas && {
            label: 'Quotas',
            id: 'quotas',
            href: ROUTES.PROJECT.DETAILS.QUOTAS.FORMAT(paramProjectName),
        },
    ].filter(Boolean) as {
        label: string;
        id: string;
        href: string;
    }[];

    return (
        <div className={styles.page}>
            <ContentLayout header={<DetailsHeader title={paramProjectName} />}>
                {showTabs && (
                    <Tabs
                        withNavigation
                        tabs={tabs}
                        activeTabId={matchQuotas ? 'quotas' : matchEvents ? 'events' : 'settings'}
                    />
                )}

                <Outlet />
            </ContentLayout>
        </div>
    );
};
