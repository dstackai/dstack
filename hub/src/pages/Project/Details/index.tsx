import React, { useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { debounce } from 'lodash';
import { useAppSelector, useBreadcrumbs, useNotifications } from 'hooks';
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
import { selectAuthToken, selectUserData } from 'App/slice';
import { useGetProjectQuery, useDeleteProjectsMutation, useUpdateProjectMembersMutation } from 'services/project';
import { ProjectMembers } from '../Members';
import styles from './styles.module.scss';
import { getProjectRoleByUserName } from '../utils';

export const ProjectDetails: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const params = useParams();
    const userData = useAppSelector(selectUserData);
    const userName = userData?.user_name ?? '';
    const userGlobalRole = userData?.global_role ?? '';
    const paramProjectName = params.name ?? '';
    const navigate = useNavigate();
    const { data, isLoading } = useGetProjectQuery({ name: paramProjectName });
    const [deleteProjects, { isLoading: isDeleting }] = useDeleteProjectsMutation();
    const [updateProjectMembers] = useUpdateProjectMembersMutation();
    const currentUserToken = useAppSelector(selectAuthToken);
    const [pushNotification] = useNotifications();

    if (data) console.log(isDeleting, !data, getProjectRoleByUserName(data, userName) !== 'admin', userGlobalRole !== 'admin');

    const isDisabledButtons = useMemo<boolean>(() => {
        return isDeleting || !data || (getProjectRoleByUserName(data, userName) !== 'admin' && userGlobalRole !== 'admin');
    }, [data, userName, userGlobalRole]);

    useBreadcrumbs([
        {
            text: t('navigation.projects'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.FORMAT(paramProjectName),
        },
    ]);

    const changeMembersHandler = (members: IProjectMember[]) => {
        updateProjectMembers({
            project_name: paramProjectName,
            members,
        })
            .unwrap()
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });
    };

    const cliCommand = `dstack config hub --url ${location.origin} --project ${paramProjectName}`;

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

        deleteProjects([paramProjectName])
            .unwrap()
            .then(() => navigate(ROUTES.PROJECT.LIST))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });

        setShowConfirmDelete(false);
    };

    const editUserHandler = () => {
        navigate(ROUTES.PROJECT.EDIT_BACKEND.FORMAT(paramProjectName));
    };

    const renderAwsSettingsSection = (): React.ReactNode => {
        if (!data) return null;

        return (
            <ColumnLayout columns={4} variant="text-grid">
                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.backend_type')}</Box>
                    <div>{t(`projects.backend_type.${data.backend.type}`)}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.aws.region_name')}</Box>
                    <div>{data.backend.region_name_title}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.aws.s3_bucket_name')}</Box>
                    <div>s3://{data.backend.s3_bucket_name}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.aws.ec2_subnet_id')}</Box>
                    <div>{data.backend.ec2_subnet_id}</div>
                </div>
            </ColumnLayout>
        );
    };

    return (
        <>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={paramProjectName}
                        deleteAction={toggleDeleteConfirm}
                        deleteDisabled={isDisabledButtons}
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
                                        <Button onClick={editUserHandler} disabled={isDisabledButtons}>
                                            {t('common.edit')}
                                        </Button>
                                    }
                                >
                                    {t('projects.edit.backend')}
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
                                    {t('projects.edit.cli')}
                                </Header>
                            }
                        >
                            <SpaceBetween size="s">
                                <Box variant="p" color="text-body-secondary">
                                    Use the code snippet below to configure your CLI to use this project as a remote
                                </Box>

                                <div className={styles.code}>
                                    <Box variant="code" color="text-status-inactive">
                                        {cliCommand}
                                    </Box>
                                </div>
                            </SpaceBetween>
                        </Container>

                        <ProjectMembers onChange={debouncedMembersHandler} initialValues={data.members} />
                    </SpaceBetween>
                )}
            </ContentLayout>

            <ConfirmationDialog visible={showDeleteConfirm} onDiscard={toggleDeleteConfirm} onConfirm={deleteUserHandler} />
        </>
    );
};
