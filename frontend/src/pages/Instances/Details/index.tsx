import React from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate, useParams } from 'react-router-dom';

import { Button, ContentLayout, DetailsHeader, Tabs } from 'components';

enum InstanceTab {
    Details = 'details',
    Events = 'events',
    Inspect = 'inspect',
}

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';
import { useGetInstanceDetailsQuery } from 'services/instance';

import { useDeleteInstance } from './useDeleteInstance';

import styles from './styles.module.scss';

export const InstanceDetailsPage: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramInstanceId = params.instanceId ?? '';
    const paramProjectName = params.projectName ?? '';
    const navigate = useNavigate();

    const { deleteInstance, isDeleting } = useDeleteInstance();

    const { data } = useGetInstanceDetailsQuery(
        {
            projectName: paramProjectName,
            instanceId: paramInstanceId,
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
            text: t('navigation.instances'),
            href: ROUTES.INSTANCES.LIST,
        },
        {
            text: data?.name ?? '',
            href: ROUTES.INSTANCES.DETAILS.FORMAT(paramProjectName, paramInstanceId),
        },
    ]);

    const deleteClickHandle = () => {
        if (!data) return;

        deleteInstance(data)
            .then(() => {
                navigate(ROUTES.INSTANCES.LIST);
            })
            .catch(console.log);
    };

    const isDisabledDeleteButton = !data || isDeleting || data.status === 'terminated';

    return (
        <div className={styles.page}>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={data?.name}
                        actionButtons={
                            <Button onClick={deleteClickHandle} disabled={isDisabledDeleteButton}>
                                {t('common.delete')}
                            </Button>
                        }
                    />
                }
            >
                <Tabs
                    withNavigation
                    tabs={[
                        {
                            label: 'Details',
                            id: InstanceTab.Details,
                            href: ROUTES.INSTANCES.DETAILS.FORMAT(paramProjectName, paramInstanceId),
                        },
                        {
                            label: 'Events',
                            id: InstanceTab.Events,
                            href: ROUTES.INSTANCES.DETAILS.EVENTS.FORMAT(paramProjectName, paramInstanceId),
                        },
                        {
                            label: 'Inspect',
                            id: InstanceTab.Inspect,
                            href: ROUTES.INSTANCES.DETAILS.INSPECT.FORMAT(paramProjectName, paramInstanceId),
                        },
                    ]}
                />

                <Outlet />
            </ContentLayout>
        </div>
    );
};
