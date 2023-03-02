import React from 'react';
import { Container, Header, Loader, ContentLayout } from 'components';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { useGetHubQuery, useUpdateHubMutation } from 'services/hub';
import { useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { HubForm } from '../Form';

export const HubEditBackend: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramHubName = params.name ?? '';
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const { data, isLoading } = useGetHubQuery({ name: paramHubName });
    const [updateHub, { isLoading: isHubUpdating }] = useUpdateHubMutation();

    useBreadcrumbs([
        {
            text: t('navigation.hubs'),
            href: ROUTES.HUB.LIST,
        },
        {
            text: paramHubName,
            href: ROUTES.HUB.DETAILS.FORMAT(paramHubName),
        },

        {
            text: t('hubs.edit.edit_backend'),
            href: ROUTES.USER.EDIT.FORMAT(paramHubName),
        },
    ]);

    const onCancelHandler = () => {
        navigate(ROUTES.HUB.DETAILS.FORMAT(paramHubName));
    };

    const onSubmitHandler = async (hubData: Partial<IHub>) => {
        try {
            const data = await updateHub({
                ...hubData,
                hub_name: paramHubName,
            }).unwrap();

            pushNotification({
                type: 'success',
                content: t('hubs.edit.success_notification'),
            });

            navigate(ROUTES.HUB.DETAILS.FORMAT(data.hub_name ?? paramHubName));
        } catch (e) {
            pushNotification({
                type: 'error',
                content: t('hubs.edit.error_notification'),
            });
        }
    };

    return (
        <ContentLayout header={<Header variant="awsui-h1-sticky">{paramHubName}</Header>}>
            {isLoading && !data && (
                <Container>
                    <Loader />
                </Container>
            )}

            {data && (
                <HubForm initialValues={data} loading={isHubUpdating} onSubmit={onSubmitHandler} onCancel={onCancelHandler} />
            )}
        </ContentLayout>
    );
};
