import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { ContentLayout, Header } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useCreateUserMutation } from 'services/user';

import { UserForm } from '../Form';

export const UserAdd: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [createUser, { isLoading }] = useCreateUserMutation();
    const [pushNotification] = useNotifications();

    useBreadcrumbs([
        {
            text: t('navigation.account'),
            href: ROUTES.USER.LIST,
        },
        {
            text: t('common.create'),
            href: ROUTES.USER.ADD,
        },
    ]);

    const onCancelHandler = () => {
        navigate(ROUTES.USER.LIST);
    };

    const onSubmitHandler = async (userData: Omit<IUser, 'token'>) => {
        try {
            const data = await createUser(userData).unwrap();

            pushNotification({
                type: 'success',
                content: t('users.create.success_notification'),
            });

            navigate(ROUTES.USER.DETAILS.FORMAT(data.username));
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
        } catch (e) {
            pushNotification({
                type: 'error',
                content: t('users.create.error_notification'),
            });
        }
    };

    return (
        <ContentLayout header={<Header variant="awsui-h1-sticky">{t('users.create.page_title')}</Header>}>
            <UserForm onSubmit={onSubmitHandler} loading={isLoading} onCancel={onCancelHandler} />
        </ContentLayout>
    );
};
