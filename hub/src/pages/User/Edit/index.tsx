import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { pick } from 'lodash';
import { useBreadcrumbs, useNotifications } from 'hooks';
import { Container, ContentLayout, Header, Loader } from 'components';
import { UserForm } from '../Form';
import { ROUTES } from 'routes';
import { useGetUserQuery, useRefreshTokenMutation, useUpdateUserMutation } from 'services/user';

export const UserEdit: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const navigate = useNavigate();
    const paramUserName = params.name ?? '';
    const { isLoading, data } = useGetUserQuery({ name: paramUserName }, { skip: !params.name });
    const [updateUser, { isLoading: isUserUpdating }] = useUpdateUserMutation();
    const [refreshToken, { isLoading: isTokenRefreshing }] = useRefreshTokenMutation();

    useBreadcrumbs([
        {
            text: t('navigation.users'),
            href: ROUTES.USER.LIST,
        },
        {
            text: paramUserName,
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
        {
            text: t('common.edit'),
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
    ]);

    const [pushNotification] = useNotifications();

    const onRefreshTokenHandler = async () => {
        try {
            await refreshToken({
                user_name: paramUserName,
            }).unwrap();

            pushNotification({
                type: 'success',
                content: t('users.edit.refresh_token_success_notification'),
            });
        } catch (e) {
            pushNotification({
                type: 'error',
                content: t('users.edit.refresh_token_error_notification'),
            });
        }
    };

    const onCancelHandler = () => {
        navigate(ROUTES.USER.DETAILS.FORMAT(paramUserName));
    };

    const onSubmitHandler = async (userData: Partial<IUser>) => {
        try {
            const data = await updateUser({
                ...pick(userData, ['global_role']),
                user_name: paramUserName,
            }).unwrap();

            pushNotification({
                type: 'success',
                content: t('users.edit.success_notification'),
            });

            navigate(ROUTES.USER.DETAILS.FORMAT(data.user_name ?? paramUserName));
        } catch (e) {
            pushNotification({
                type: 'error',
                content: t('users.edit.error_notification'),
            });
        }
    };

    return (
        <ContentLayout header={<Header variant="awsui-h1-sticky">{paramUserName}</Header>}>
            {isLoading && !data && (
                <Container>
                    <Loader />
                </Container>
            )}

            {data && (
                <UserForm
                    initialValues={data}
                    onSubmit={onSubmitHandler}
                    loading={isUserUpdating}
                    onCancel={onCancelHandler}
                    onRefreshToken={onRefreshTokenHandler}
                    disabledRefreshToken={isTokenRefreshing}
                />
            )}
        </ContentLayout>
    );
};
