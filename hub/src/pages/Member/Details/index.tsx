import React, { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ContentLayout, SpaceBetween, Container, Header, ColumnLayout, Box } from 'components';
import { DetailsHeader } from 'components';
import { useTranslation } from 'react-i18next';
import { useDeleteUsersMutation, useGetUserQuery } from 'services/user';
import { ROUTES } from 'routes';

export const MemberDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const navigate = useNavigate();
    const { data } = useGetUserQuery({ name: params.name ?? '' }, { skip: !params.name });
    const [deleteUsers, { isLoading: isDeleting, data: deleteData }] = useDeleteUsersMutation();

    useEffect(() => {
        if (!isDeleting && deleteData) navigate(ROUTES.MEMBER.LIST);
    }, [isDeleting, deleteData]);

    const deleteSUserHandler = () => {
        if (!data) return;
        deleteUsers([data.user_name]);
    };

    return (
        <ContentLayout
            header={
                <DetailsHeader
                    title={data?.user_name}
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
                                    <Box variant="awsui-key-label">{t('users.email')}</Box>
                                    <div>{data.email}</div>
                                </div>
                            </SpaceBetween>

                            <SpaceBetween size="l">
                                <div>
                                    <Box variant="awsui-key-label">{t('users.token')}</Box>
                                    <div>{data.token}</div>
                                </div>
                                <div>
                                    <Box variant="awsui-key-label">{t('users.permission_level')}</Box>
                                    <div>{data.permission_level}</div>
                                </div>
                            </SpaceBetween>
                        </ColumnLayout>
                    </Container>
                </SpaceBetween>
            )}
        </ContentLayout>
    );
};
