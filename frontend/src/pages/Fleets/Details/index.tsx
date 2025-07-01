import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { format } from 'date-fns';

import {
    Box,
    Button,
    ColumnLayout,
    Container,
    ContentLayout,
    DetailsHeader,
    Header,
    Loader,
    NavigateLink,
    StatusIndicator,
} from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs } from 'hooks';
import { getFleetInstancesLinkText, getFleetPrice, getFleetStatusIconType } from 'libs/fleet';
import { ROUTES } from 'routes';
import { useGetFleetDetailsQuery } from 'services/fleet';

import { useDeleteFleet } from '../List/useDeleteFleet';

export const FleetDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramFleetId = params.fleetId ?? '';
    const paramProjectName = params.projectName ?? '';
    const navigate = useNavigate();

    const { deleteFleets, isDeleting } = useDeleteFleet();

    const { data, isLoading } = useGetFleetDetailsQuery(
        {
            projectName: paramProjectName,
            fleetId: paramFleetId,
        },
        {
            refetchOnMountOrArgChange: true,
        },
    );

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
            text: data?.name ?? '',
            href: ROUTES.FLEETS.DETAILS.FORMAT(paramProjectName, paramFleetId),
        },
    ]);

    const deleteClickHandle = () => {
        if (!data) return;

        deleteFleets([data])
            .then(() => {
                navigate(ROUTES.FLEETS.LIST);
            })
            .catch(console.log);
    };

    const renderPrice = (fleet: IFleet) => {
        const price = getFleetPrice(fleet);

        if (typeof price === 'number') return `$${price}`;

        return '-';
    };

    const isDisabledDeleteButton = !data || isDeleting;

    return (
        <ContentLayout
            header={
                <DetailsHeader
                    title={data?.name}
                    actionButtons={
                        <>
                            <Button onClick={deleteClickHandle} disabled={isDisabledDeleteButton}>
                                {t('common.delete')}
                            </Button>
                        </>
                    }
                />
            }
        >
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
                            <Box variant="awsui-key-label">{t('fleets.instances.title')}</Box>

                            <div>
                                <NavigateLink href={ROUTES.INSTANCES.LIST + `?fleet_ids=${data.id}`}>
                                    {getFleetInstancesLinkText(data)}
                                </NavigateLink>
                            </div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.started')}</Box>
                            <div>{format(new Date(data.created_at), DATE_TIME_FORMAT)}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.price')}</Box>
                            <div>{renderPrice(data)}</div>
                        </div>
                    </ColumnLayout>
                </Container>
            )}
        </ContentLayout>
    );
};
