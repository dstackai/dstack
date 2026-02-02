import React from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useParams } from 'react-router-dom';

import { ContentLayout, DetailsHeader, NavigateLink } from 'components';

import { ROUTES } from 'routes';

export const ProjectDetails: React.FC = () => {
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const { t } = useTranslation();

    return (
        <ContentLayout
            header={
                <DetailsHeader
                    title={paramProjectName}
                    actionButtons={
                        <NavigateLink href={ROUTES.EVENTS.LIST + `?within_projects=${paramProjectName}`}>
                            {t('projects.events')}
                        </NavigateLink>
                    }
                />
            }
        >
            <Outlet />
        </ContentLayout>
    );
};
