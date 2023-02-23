import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ContentLayout, SpaceBetween, Container, Header, ColumnLayout, Box, Loader, ConfirmationDialog } from 'components';
import { DetailsHeader } from 'components';
import { useTranslation } from 'react-i18next';
import { useBreadcrumbs } from 'hooks';
import { useDeleteUsersMutation, useGetUserQuery } from 'services/user';
import { ROUTES } from 'routes';
import Button from '@cloudscape-design/components/button';

export const UserDetails: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const params = useParams();
    const paramUserName = params.name ?? '';
    const navigate = useNavigate();
    const { isLoading, data } = useGetUserQuery({ name: paramUserName }, { skip: !params.name });
    const [deleteUsers, { isLoading: isDeleting, data: deleteData }] = useDeleteUsersMutation();

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

    useEffect(() => {
        if (!isDeleting && deleteData) navigate(ROUTES.USER.LIST);
    }, [isDeleting, deleteData]);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const deleteUserHandler = () => {
        if (!data) return;
        deleteUsers([paramUserName]);
        setShowConfirmDelete(false);
    };

    const editUserHandler = () => {
        navigate(ROUTES.USER.EDIT.FORMAT(paramUserName));
    };

    return (
        <>
            <ContentLayout
                header={<DetailsHeader title={paramUserName} deleteAction={toggleDeleteConfirm} deleteDisabled={isDeleting} />}
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
                                        <Button onClick={editUserHandler} disabled={isDeleting}>
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
                                    <div>
                                        <Box variant="awsui-key-label">{t('users.user_name')}</Box>
                                        <div>{data.user_name}</div>
                                    </div>

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
