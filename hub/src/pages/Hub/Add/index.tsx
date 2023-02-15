import React from 'react';
import { ContentLayout, Header } from 'components';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { HubForm } from '../Form';
import { useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useCreateHubMutation } from 'services/hub';

export const HubAdd: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [createHub, { isLoading }] = useCreateHubMutation();

    useBreadcrumbs([
        {
            text: t('navigation.hubs'),
            href: ROUTES.HUB.LIST,
        },
        {
            text: t('common.create'),
            href: ROUTES.HUB.ADD,
        },
    ]);

    const onCancelHandler = () => {
        navigate(ROUTES.HUB.LIST);
    };

    const onSubmitHandler = async (hubData: IHub) => {
        try {
            const data = await createHub(hubData).unwrap();

            pushNotification({
                type: 'success',
                content: t('hubs.create.success_notification'),
            });

            navigate(ROUTES.HUB.DETAILS.FORMAT(data.hub_name));
        } catch (e) {
            pushNotification({
                type: 'error',
                content: t('hubs.create.error_notification'),
            });
        }
    };

    return (
        <ContentLayout header={<Header variant="awsui-h1-sticky">{t('hubs.create.page_title')}</Header>}>
            <HubForm onSubmit={onSubmitHandler} loading={isLoading} onCancel={onCancelHandler} />
        </ContentLayout>
    );
};
