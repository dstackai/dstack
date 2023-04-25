import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import {
    Box,
    Button,
    ColumnLayout,
    ConfirmationDialog,
    Container,
    ContentLayout,
    Header,
    Loader,
    SpaceBetween,
} from 'components';
import { DetailsHeader } from 'components';

import { useAppSelector, useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useDeleteUsersMutation, useGetUserQuery } from 'services/user';

import { selectUserData } from 'App/slice';

export const UserDetails: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const userData = useAppSelector(selectUserData);
    const userGlobalRole = userData?.global_role ?? '';
    const params = useParams();
    const paramUserName = params.name ?? '';
    const navigate = useNavigate();
    const { isLoading, data } = useGetUserQuery({ name: paramUserName }, { skip: !params.name });
    const [deleteUsers, { isLoading: isDeleting }] = useDeleteUsersMutation();
    const [pushNotification] = useNotifications();

    useBreadcrumbs([
        {
            text: t('navigation.users'),
            href: ROUTES.USER.LIST,
        },
        {
            text: paramUserName,
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
    ]);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const deleteUserHandler = () => {
        if (!data) return;

        deleteUsers([paramUserName])
            .unwrap()
            .then(() => navigate(ROUTES.USER.LIST))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });

        setShowConfirmDelete(false);
    };

    const editUserHandler = () => {
        navigate(ROUTES.USER.EDIT.FORMAT(paramUserName));
    };

    return (
        <>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={paramUserName}
                        deleteAction={toggleDeleteConfirm}
                        deleteDisabled={isDeleting || userGlobalRole !== 'admin'}
                    />
                }
            >
                {isLoading && !data && (
                    <Container>
                        <Loader />
                    </Container>
                )}

                {data && (
                    <SpaceBetween size="l">
                        <Container
                            header={
                                <Header
                                    variant="h2"
                                    actions={
                                        <Button onClick={editUserHandler} disabled={isDeleting || userGlobalRole !== 'admin'}>
                                            {t('common.edit')}
                                        </Button>
                                    }
                                >
                                    {t('users.account_settings')}
                                </Header>
                            }
                        >
                            <ColumnLayout columns={2} variant="text-grid">
                                <SpaceBetween size="l">
                                    {/*<div>*/}
                                    {/*    <Box variant="awsui-key-label">{t('users.user_name')}</Box>*/}
                                    {/*    <div>{data.user_name}</div>*/}
                                    {/*</div>*/}

                                    <div>
                                        <Box variant="awsui-key-label">{t('users.global_role')}</Box>
                                        <div>{t(`roles.${data.global_role}`)}</div>
                                    </div>
                                </SpaceBetween>
                            </ColumnLayout>
                        </Container>
                    </SpaceBetween>
                )}
            </ContentLayout>

            <ConfirmationDialog visible={showDeleteConfirm} onDiscard={toggleDeleteConfirm} onConfirm={deleteUserHandler} />
        </>
    );
};
