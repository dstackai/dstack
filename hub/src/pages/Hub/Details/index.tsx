import React, { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { debounce } from 'lodash';
import { useAppSelector, useBreadcrumbs } from 'hooks';
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
    SpaceBetween,
    Button,
    StatusIndicator,
    Popover,
} from 'components';
import { selectAuthToken } from 'App/slice';
import { useGetHubQuery, useDeleteHubsMutation, useUpdateHubMembersMutation } from 'services/hub';
import { HubMembers } from '../Members';
import styles from './styles.module.scss';

export const HubDetails: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const params = useParams();
    const paramHubName = params.name ?? '';
    const navigate = useNavigate();
    const { data, isLoading } = useGetHubQuery({ name: paramHubName });
    const [deleteHubs, { isLoading: isDeleting, data: deleteData }] = useDeleteHubsMutation();
    const [updateHubMembers] = useUpdateHubMembersMutation();
    const currentUserToken = useAppSelector(selectAuthToken);

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

    useEffect(() => {
        if (!isDeleting && deleteData) navigate(ROUTES.HUB.LIST);
    }, [isDeleting, deleteData]);

    const changeMembersHandler = (members: IHubMember[]) => {
        updateHubMembers({
            hub_name: paramHubName,
            members,
        });
    };

    const cliCommand = `dstack config hub --url ${location.origin}/${paramHubName} --token ${currentUserToken}`;

    const onCopyCliCommand = async () => {
        try {
            await navigator.clipboard.writeText(cliCommand);
        } catch (err) {
            console.error('Failed to copy: ', err);
        }
    };

    const debouncedMembersHandler = useCallback(debounce(changeMembersHandler, 1000), []);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const deleteUserHandler = () => {
        if (!data) return;
        deleteHubs([paramHubName]);
        setShowConfirmDelete(false);
    };

    const editUserHandler = () => {
        navigate(ROUTES.HUB.EDIT_BACKEND.FORMAT(paramHubName));
    };

    const renderAwsSettingsSection = (): React.ReactNode => {
        if (!data) return null;

        return (
            <ColumnLayout columns={4} variant="text-grid">
                <div>
                    <Box variant="awsui-key-label">{t('hubs.edit.backend_type')}</Box>
                    <div>{t(`hubs.backend_type.${data.backend.type}`)}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('hubs.edit.aws.region_name')}</Box>
                    <div>{data.backend.region_name_title}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('hubs.edit.aws.s3_bucket_name')}</Box>
                    <div>s3://{data.backend.s3_bucket_name}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('hubs.edit.aws.ec2_subnet_id')}</Box>
                    <div>{data.backend.ec2_subnet_id}</div>
                </div>
            </ColumnLayout>
        );
    };

    return (
        <>
            <ContentLayout
                header={<DetailsHeader title={paramHubName} deleteAction={toggleDeleteConfirm} deleteDisabled={isDeleting} />}
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
                                    {t('hubs.edit.backend')}
                                </Header>
                            }
                        >
                            {renderAwsSettingsSection()}
                        </Container>
                        <Container
                            header={
                                <Header
                                    variant="h2"
                                    actions={
                                        <Popover
                                            dismissButton={false}
                                            position="top"
                                            size="small"
                                            triggerType="custom"
                                            content={<StatusIndicator type="success">{t('common.copied')}</StatusIndicator>}
                                        >
                                            <Button
                                                formAction="none"
                                                iconName="copy"
                                                variant="normal"
                                                onClick={onCopyCliCommand}
                                            >
                                                {t('common.copy')}
                                            </Button>
                                        </Popover>
                                    }
                                >
                                    {t('hubs.edit.cli')}
                                </Header>
                            }
                        >
                            <SpaceBetween size="s">
                                <Box variant="p" color="text-body-secondary">
                                    Use the code snippet below to configure your CLI to use this hub as a remote
                                </Box>

                                <div className={styles.code}>
                                    <Box variant="code" color="text-status-inactive">
                                        {cliCommand}
                                    </Box>
                                </div>
                            </SpaceBetween>
                        </Container>

                        <HubMembers onChange={debouncedMembersHandler} initialValues={data.members} />
                    </SpaceBetween>
                )}
            </ContentLayout>

            <ConfirmationDialog visible={showDeleteConfirm} onDiscard={toggleDeleteConfirm} onConfirm={deleteUserHandler} />
        </>
    );
};
