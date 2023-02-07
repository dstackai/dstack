import React, { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ContentLayout, SpaceBetween, Container, Header, ColumnLayout, Box } from 'components';
import { DetailsHeader } from 'components';
import { useTranslation } from 'react-i18next';
import { useBreadcrumbs } from 'hooks';
import { useDeleteUsersMutation, useGetUserQuery } from 'services/user';
import { ROUTES } from 'routes';

export const UserDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramUserName = params.name ?? '';
    const navigate = useNavigate();
    const { data } = useGetUserQuery({ name: paramUserName }, { skip: !params.name });
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

    const deleteSUserHandler = () => {
        if (!data) return;
        deleteUsers([paramUserName]);
    };

    return (
        <ContentLayout
            header={
                <DetailsHeader
                    title={paramUserName}
                    editAction={() => console.log('edit')}
                    deleteAction={deleteSUserHandler}
                    editDisabled={isDeleting}
                    deleteDisabled={isDeleting}
                />
            }
        >
            {data && (
                <SpaceBetween size="l">
                    <Container header={<Header variant="h2">{t('users.general_info')}</Header>}>
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
    );
};
