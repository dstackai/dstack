import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { pick } from 'lodash';

import { Box, ConfirmationDialog, Container, ContentLayout, Header, Loader } from 'components';

import { useAppDispatch, useAppSelector, useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useGetUserQuery, useRefreshTokenMutation, useUpdateUserMutation } from 'services/user';

import { selectUserData, setAuthData } from 'App/slice';

import { UserForm } from '../Form';

export const UserEdit: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const navigate = useNavigate();
    const userData = useAppSelector(selectUserData);
    const userGlobalRole = userData?.global_role ?? '';
    const paramUserName = params.userName ?? '';
    const dispatch = useAppDispatch();
    const [showRefreshConfirm, setShowRefreshConfirm] = useState(false);
    const { isLoading, data } = useGetUserQuery({ name: paramUserName }, { skip: !paramUserName });
    const [updateUser, { isLoading: isUserUpdating }] = useUpdateUserMutation();
    const [refreshToken, { isLoading: isTokenRefreshing }] = useRefreshTokenMutation();

    const toggleRefreshConfirm = () => {
        setShowRefreshConfirm((val) => !val);
    };

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
            text: t('common.settings'),
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
        {
            text: t('common.edit'),
            href: ROUTES.USER.EDIT.FORMAT(paramUserName),
        },
    ]);

    const [pushNotification] = useNotifications();

    const onRefreshTokenHandler = async () => {
        setShowRefreshConfirm(false);

        try {
            await refreshToken({
                username: paramUserName,
            })
                .unwrap()
                .then(({ creds: { token } }) => {
                    if (paramUserName === userData?.username) {
                        dispatch(setAuthData({ token }));
                    }
                });

            pushNotification({
                type: 'success',
                content: t('users.edit.refresh_token_success_notification'),
            });
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
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
                ...pick(userData, ['global_role', 'email', 'active']),
                username: paramUserName,
            }).unwrap();

            pushNotification({
                type: 'success',
                content: t('users.edit.success_notification'),
            });

            navigate(ROUTES.USER.DETAILS.FORMAT(data.username ?? paramUserName));
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
        } catch (e) {
            pushNotification({
                type: 'error',
                content: t('users.edit.error_notification'),
            });
        }
    };

    return (
        <>
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
                        onRefreshToken={toggleRefreshConfirm}
                        disabledEmailEndRoleFields={userGlobalRole !== 'admin'}
                        disabledRefreshToken={isTokenRefreshing}
                    />
                )}
            </ContentLayout>

            <ConfirmationDialog
                title={t('users.edit.refresh_token_confirm_title')}
                content={<Box variant="span">{t('users.edit.refresh_token_confirm_message')}</Box>}
                confirmButtonLabel={t('users.edit.refresh_token_button_label')}
                visible={showRefreshConfirm}
                onDiscard={toggleRefreshConfirm}
                onConfirm={onRefreshTokenHandler}
            />
        </>
    );
};
