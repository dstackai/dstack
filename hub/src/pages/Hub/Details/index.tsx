import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { Table } from 'components';
import { useBreadcrumbs, useCollection } from 'hooks';
import { ROUTES } from 'routes';
import {
    Box,
    ColumnLayout,
    ConfirmationDialog,
    Container,
    ContentLayout,
    DetailsHeader,
    Header,
    Loader,
    NavigateLink,
    SpaceBetween,
} from 'components';
import { useGetHubQuery, useDeleteHubsMutation } from 'services/hub';

export const HubDetails: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const params = useParams();
    const paramHubName = params.name ?? '';
    const navigate = useNavigate();
    const { data, isLoading } = useGetHubQuery({ name: paramHubName });
    const [deleteHubs, { isLoading: isDeleting, data: deleteData }] = useDeleteHubsMutation();

    useBreadcrumbs([
        {
            text: t('navigation.hubs'),
            href: ROUTES.HUB.LIST,
        },
        {
            text: paramHubName,
            href: ROUTES.HUB.DETAILS.FORMAT(paramHubName),
        },
    ]);

    const { items } = useCollection(data?.members ?? [], {});

    useEffect(() => {
        if (!isDeleting && deleteData) navigate(ROUTES.HUB.LIST);
    }, [isDeleting, deleteData]);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const deleteUserHandler = () => {
        if (!data) return;
        deleteHubs([paramHubName]);
        setShowConfirmDelete(false);
    };

    const editUserHandler = () => {
        navigate(ROUTES.HUB.EDIT.FORMAT(paramHubName));
    };

    const renderAwsSettingsSection = (): React.ReactNode => {
        if (!data) return null;

        return (
            <>
                <SpaceBetween size="xxl">
                    <div>
                        <Box variant="awsui-key-label">{t('hubs.edit.backend_type')}</Box>
                        <div>{t(`hubs.backend_type.${data.backend.type}`)}</div>
                    </div>

                    <ColumnLayout columns={2} variant="text-grid">
                        <SpaceBetween size="l">
                            <div>
                                <Box variant="awsui-key-label">{t('hubs.edit.aws.access_key')}</Box>
                                <div>{t(`hubs.backend_type.${data.backend.access_key}`)}</div>
                            </div>
                            <div>
                                <Box variant="awsui-key-label">{t('hubs.edit.aws.region_name')}</Box>
                                <div>{t(`hubs.backend_type.${data.backend.region_name}`)}</div>
                            </div>
                            <div>
                                <Box variant="awsui-key-label">{t('hubs.edit.aws.ec2_subnet_id')}</Box>
                                <div>{t(`hubs.backend_type.${data.backend.ec2_subnet_id}`)}</div>
                            </div>
                        </SpaceBetween>

                        <SpaceBetween size="l">
                            <div>
                                <Box variant="awsui-key-label">{t('hubs.edit.aws.secret_key')}</Box>
                                <div>{t(`hubs.backend_type.${data.backend.secret_key}`)}</div>
                            </div>
                            <div>
                                <Box variant="awsui-key-label">{t('hubs.edit.aws.s3_bucket_name')}</Box>
                                <div>{t(`hubs.backend_type.${data.backend.s3_bucket_name}`)}</div>
                            </div>
                        </SpaceBetween>
                    </ColumnLayout>
                </SpaceBetween>
            </>
        );
    };

    const renderMembersSection = (): React.ReactNode => {
        const COLUMN_DEFINITIONS = [
            {
                id: 'name',
                header: t('hubs.edit.members.name'),
                cell: (item: IHubMember) => (
                    <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(item.user_name)}>{item.user_name}</NavigateLink>
                ),
            },
            {
                id: 'global_role',
                header: t('hubs.edit.members.role'),
                cell: (item: IHubMember) => t(`roles.${item.hub_role}`),
            },
        ];

        return (
            <Table
                columnDefinitions={COLUMN_DEFINITIONS}
                items={items}
                header={
                    <Header variant="h2" counter={`(${items.length})`}>
                        {t('hubs.edit.members.section_title')}
                    </Header>
                }
            />
        );
    };

    return (
        <>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={paramHubName}
                        editAction={editUserHandler}
                        editDisabled={isDeleting}
                        deleteAction={toggleDeleteConfirm}
                        deleteDisabled={isDeleting}
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
                        <Container header={<Header variant="h2">{t('hubs.edit.cloud_settings')}</Header>}>
                            {renderAwsSettingsSection()}
                        </Container>

                        {renderMembersSection()}
                    </SpaceBetween>
                )}
            </ContentLayout>

            <ConfirmationDialog visible={showDeleteConfirm} onDiscard={toggleDeleteConfirm} onConfirm={deleteUserHandler} />
        </>
    );
};
