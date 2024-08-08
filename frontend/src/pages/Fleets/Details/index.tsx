import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Container, ContentLayout, DetailsHeader, Loader } from 'components';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';
import { useGetPoolDetailsQuery } from 'services/pool';

import { Instances } from './Instances';

export const FleetDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramPoolName = params.poolName ?? '';
    const paramProjectName = params.projectName ?? '';

    const { data, isLoading } = useGetPoolDetailsQuery({
        projectName: paramProjectName,
        poolName: paramPoolName,
    });

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
            text: t('navigation.fleets'),
            href: ROUTES.FLEETS.LIST,
        },
        {
            text: paramPoolName,
            href: ROUTES.FLEETS.DETAILS.FORMAT(paramProjectName, paramPoolName),
        },
    ]);

    return (
        <ContentLayout header={<DetailsHeader title={paramPoolName} />}>
            {isLoading && (
                <Container>
                    <Loader />
                </Container>
            )}

            {data && <Instances data={data.instances} />}
        </ContentLayout>
    );
};
