import React from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate, useParams } from 'react-router-dom';

import { Button, ContentLayout, DetailsHeader, Tabs } from 'components';

enum CodeTab {
    Details = 'details',
    Events = 'events',
}

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';
import { useGetFleetDetailsQuery } from 'services/fleet';

import { useDeleteFleet } from '../List/useDeleteFleet';

import styles from './styles.module.scss';

export const FleetDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramFleetId = params.fleetId ?? '';
    const paramProjectName = params.projectName ?? '';
    const navigate = useNavigate();

    const { deleteFleets, isDeleting } = useDeleteFleet();

    const { data } = useGetFleetDetailsQuery(
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

    const isDisabledDeleteButton = !data || isDeleting;

    return (
        <div className={styles.page}>
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
                <Tabs
                    withNavigation
                    tabs={[
                        {
                            label: 'Details',
                            id: CodeTab.Details,
                            href: ROUTES.FLEETS.DETAILS.FORMAT(paramProjectName, paramFleetId),
                        },
                        {
                            label: 'Events',
                            id: CodeTab.Events,
                            href: ROUTES.FLEETS.DETAILS.EVENTS.FORMAT(paramProjectName, paramFleetId),
                        },
                    ]}
                />

                <Outlet />
            </ContentLayout>
        </div>
    );
};
