import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Container, ContentLayout, DetailsHeader, Loader } from 'components';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';
import { useGetFleetDetailsQuery } from 'services/fleet';

import { Instances } from './Instances';

export const FleetDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramFleetName = params.fleetName ?? '';
    const paramProjectName = params.projectName ?? '';

    const { data, isLoading } = useGetFleetDetailsQuery({
        projectName: paramProjectName,
        fleetName: paramFleetName,
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
            text: paramFleetName,
            href: ROUTES.FLEETS.DETAILS.FORMAT(paramProjectName, paramFleetName),
        },
    ]);

    return (
        <ContentLayout header={<DetailsHeader title={paramFleetName} />}>
            {isLoading && (
                <Container>
                    <Loader />
                </Container>
            )}

            {data && <Instances data={data.instances} />}
        </ContentLayout>
    );
};
