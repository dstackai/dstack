import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { format } from 'date-fns';

import {
    Box,
    ColumnLayout,
    Container,
    ContentLayout,
    DetailsHeader,
    Header,
    Icon,
    Loader,
    NavigateLink,
    StatusIndicator,
} from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs } from 'hooks';
import { getFleetStatusIconType } from 'libs/fleet';
import { ROUTES } from 'routes';
import { useGetFleetDetailsQuery } from 'services/fleet';

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

            {data && (
                <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                    <ColumnLayout columns={4} variant="text-grid">
                        <div>
                            <Box variant="awsui-key-label">{t('fleets.fleet')}</Box>
                            <div>{data.name}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.status')}</Box>

                            <div>
                                <StatusIndicator type={getFleetStatusIconType(data.status)}>
                                    {t(`fleets.statuses.${data.status}`)}
                                </StatusIndicator>
                            </div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.project')}</Box>

                            <div>
                                <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(data.project_name)}>
                                    {data.project_name}
                                </NavigateLink>
                            </div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.backend')}</Box>
                            <div>{data.spec.configuration?.backends?.join(', ')}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.region')}</Box>
                            <div>{data.spec.configuration.regions?.join(', ')}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.region')}</Box>
                            <div>{data.spec.configuration?.spot_policy === 'spot' && <Icon name={'check'} />}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.started')}</Box>
                            <div>{format(new Date(data.created_at), DATE_TIME_FORMAT)}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.price')}</Box>
                            <div>{data.spec.configuration?.max_price && `$${data.spec.configuration?.max_price}`}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.title')}</Box>

                            <div>
                                <NavigateLink href={ROUTES.INSTANCES.LIST + `?fleetId=${data.id}`}>
                                    Show fleet's instances
                                </NavigateLink>
                            </div>
                        </div>
                    </ColumnLayout>
                </Container>
            )}
        </ContentLayout>
    );
};
