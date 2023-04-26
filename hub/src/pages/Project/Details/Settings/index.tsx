import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { debounce } from 'lodash';

import { Box, Button, ColumnLayout, Container, Header, Loader, Popover, SpaceBetween, StatusIndicator } from 'components';

import { useAppSelector, useBreadcrumbs, useNotifications } from 'hooks';
import { copyToClipboard } from 'libs';
import { ROUTES } from 'routes';
import { useDeleteProjectsMutation, useGetProjectQuery, useUpdateProjectMembersMutation } from 'services/project';

import { selectAuthToken, selectUserData } from 'App/slice';

import { ProjectMembers } from '../../Members';
import { getProjectRoleByUserName } from '../../utils';

import styles from './styles.module.scss';

export const ProjectSettings: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const userData = useAppSelector(selectUserData);
    const userName = userData?.user_name ?? '';
    const userGlobalRole = userData?.global_role ?? '';
    const paramProjectName = params.name ?? '';
    const navigate = useNavigate();
    const { data, isLoading } = useGetProjectQuery({ name: paramProjectName });
    const [updateProjectMembers] = useUpdateProjectMembersMutation();
    const [, { isLoading: isDeleting }] = useDeleteProjectsMutation();
    const currentUserToken = useAppSelector(selectAuthToken);
    const [pushNotification] = useNotifications();

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
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            text: t('projects.settings'),
            href: ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName),
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

    const cliCommand = `dstack config hub --url ${location.origin} --project ${paramProjectName} --token ${currentUserToken}`;

    const onCopyCliCommand = () => {
        copyToClipboard(cliCommand);
    };

    const debouncedMembersHandler = useCallback(debounce(changeMembersHandler, 1000), []);

    const editUserHandler = () => {
        navigate(ROUTES.PROJECT.EDIT_BACKEND.FORMAT(paramProjectName));
    };

    const renderAwsBackendDetails = (): React.ReactNode => {
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
                    <div>{data.backend.s3_bucket_name}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.aws.ec2_subnet_id')}</Box>
                    <div>{data.backend.ec2_subnet_id}</div>
                </div>
            </ColumnLayout>
        );
    };

    const renderGCPBackendDetails = (): React.ReactNode => {
        if (!data) return null;

        return (
            <ColumnLayout columns={4} variant="text-grid">
                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.backend_type')}</Box>
                    <div>{t(`projects.backend_type.${data.backend.type}`)}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.area')}</Box>
                    <div>{data.backend.area}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.region')}</Box>
                    <div>{data.backend.region}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.zone')}</Box>
                    <div>{data.backend.zone}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.bucket_name')}</Box>
                    <div>{data.backend.bucket_name}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.vpc')}</Box>
                    <div>{data.backend.vpc}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.subnet')}</Box>
                    <div>{data.backend.subnet}</div>
                </div>
            </ColumnLayout>
        );
    };

    const renderBackendDetails = () => {
        switch (data?.backend.type) {
            case 'aws': {
                return renderAwsBackendDetails();
            }
            case 'gcp': {
                return renderGCPBackendDetails();
            }
            default:
                return null;
        }
    };

    return (
        <>
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
                        {renderBackendDetails()}
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
                                        <Button formAction="none" iconName="copy" variant="normal" onClick={onCopyCliCommand}>
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
                                Run the command below to configure this project as a remote
                            </Box>

                            <div className={styles.code}>
                                <Box variant="code" color="text-status-inactive">
                                    {cliCommand}
                                </Box>
                            </div>
                        </SpaceBetween>
                    </Container>

                    <ProjectMembers
                        onChange={debouncedMembersHandler}
                        initialValues={data.members}
                        readonly={userGlobalRole !== 'admin'}
                    />
                </SpaceBetween>
            )}
        </>
    );
};
