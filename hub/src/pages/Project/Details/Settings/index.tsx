import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { debounce } from 'lodash';

import { Box, Button, ColumnLayout, Container, Header, Loader, Popover, SpaceBetween, StatusIndicator } from 'components';

import { useAppSelector, useBreadcrumbs, useNotifications } from 'hooks';
import { copyToClipboard } from 'libs';
import { ROUTES } from 'routes';
import { useDeleteProjectBackendMutation, useGetProjectBackendsQuery } from 'services/backend';
import { useGetProjectQuery, useUpdateProjectMembersMutation } from 'services/project';

import { selectAuthToken, selectUserData } from 'App/slice';

import { ProjectMembers } from '../../Members';
import { getLambdaStorageTypeLabel } from '../../utils';

import { BackendTypesEnum } from '../../Backends/Form/types';

import styles from './styles.module.scss';

export const ProjectSettings: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const userData = useAppSelector(selectUserData);
    const userGlobalRole = userData?.global_role ?? '';
    const paramProjectName = params.name ?? '';
    const navigate = useNavigate();
    const { data, isLoading } = useGetProjectQuery({ name: paramProjectName });
    const { data: backendsData, isLoading: isLoadingBackends } = useGetProjectBackendsQuery({ projectName: paramProjectName });
    const [updateProjectMembers] = useUpdateProjectMembersMutation();
    const [deleteBackend, { isLoading: isDeleting, originalArgs: deleteArgs }] = useDeleteProjectBackendMutation();

    const currentUserToken = useAppSelector(selectAuthToken);
    const [pushNotification] = useNotifications();

    const isLoadingPage = isLoading || !data || isLoadingBackends;

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

    const cliCommand = `dstack config --url ${location.origin} --project ${paramProjectName} --token ${currentUserToken}`;

    const onCopyCliCommand = () => {
        copyToClipboard(cliCommand);
    };

    const debouncedMembersHandler = useCallback(debounce(changeMembersHandler, 1000), []);

    const renderAwsBackendDetails = (backend: IBackendAWSWithTitles): React.ReactNode => {
        if (!data) return null;

        const extraRegions = backend.extra_regions?.join(', ');

        return (
            <ColumnLayout columns={4} variant="text-grid">
                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.backend_type')}</Box>
                    <div>{t(`backend.type.${backend.type}`)}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.aws.region_name')}</Box>
                    <div>{backend.region_name_title}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.aws.s3_bucket_name')}</Box>
                    <div>{backend.s3_bucket_name}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.aws.ec2_subnet_id')}</Box>
                    <div>{backend.ec2_subnet_id || '-'}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.aws.extra_regions')}</Box>

                    <div style={{ whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }} title={extraRegions}>
                        {extraRegions || '-'}
                    </div>
                </div>
            </ColumnLayout>
        );
    };

    const renderAzureBackendDetails = (backend: IBackendAzure): React.ReactNode => {
        if (!data) return null;

        return (
            <ColumnLayout columns={4} variant="text-grid">
                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.backend_type')}</Box>
                    <div>{t(`backend.type.${backend.type}`)}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.azure.location')}</Box>
                    <div>{backend.location}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.azure.storage_account')}</Box>
                    <div>{backend.storage_account}</div>
                </div>
            </ColumnLayout>
        );
    };

    const renderGCPBackendDetails = (backend: IBackendGCP): React.ReactNode => {
        if (!data) return null;

        return (
            <ColumnLayout columns={4} variant="text-grid">
                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.backend_type')}</Box>
                    <div>{t(`backend.type.${backend.type}`)}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.area')}</Box>
                    <div>{backend.area}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.region')}</Box>
                    <div>{backend.region}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.zone')}</Box>
                    <div>{backend.zone}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.bucket_name')}</Box>
                    <div>{backend.bucket_name}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.vpc')}</Box>
                    <div>{backend.vpc}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.gcp.subnet')}</Box>
                    <div>{backend.subnet}</div>
                </div>
            </ColumnLayout>
        );
    };

    const renderLambdaBackendDetails = (backend: IBackendLambda): React.ReactNode => {
        if (!data) return null;

        const regions = backend.regions ? backend.regions.join(', ') : '';

        return (
            <ColumnLayout columns={4} variant="text-grid">
                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.backend_type')}</Box>
                    <div>{t(`backend.type.${backend.type}`)}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.lambda.regions')}</Box>
                    <div style={{ whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }} title={regions}>
                        {regions}
                    </div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.lambda.storage_backend.type')}</Box>
                    <div>{getLambdaStorageTypeLabel(backend.storage_backend.type)}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.lambda.storage_backend.s3_bucket_name')}</Box>
                    <div>{backend.storage_backend.bucket_name}</div>
                </div>
            </ColumnLayout>
        );
    };

    const renderLocalBackendDetails = (backend: IBackendLocal): React.ReactNode => {
        if (!data) return null;

        return (
            <ColumnLayout variant="text-grid">
                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.backend_type')}</Box>
                    <div>{t(`backend.type.${backend.type}`)}</div>
                </div>

                <div>
                    <Box variant="awsui-key-label">{t('projects.edit.local.path')}</Box>
                    <div>{backend.path}</div>
                </div>
            </ColumnLayout>
        );
    };

    const renderBackendDetails = (backend: IProjectBackend) => {
        switch (backend.config.type) {
            case BackendTypesEnum.AWS: {
                return renderAwsBackendDetails(backend.config);
            }
            case BackendTypesEnum.AZURE: {
                return renderAzureBackendDetails(backend.config);
            }
            case BackendTypesEnum.GCP: {
                return renderGCPBackendDetails(backend.config);
            }
            case BackendTypesEnum.LAMBDA: {
                return renderLambdaBackendDetails(backend.config);
            }
            case 'local': {
                return renderLocalBackendDetails(backend.config);
            }
            default:
                return null;
        }
    };

    const goToBackendDetails = (backendName: IProjectBackend['name']) => {
        navigate(ROUTES.PROJECT.BACKEND.EDIT.FORMAT(paramProjectName, backendName));
    };

    const getDeleteBackendAction = (backendName: IProjectBackend['name']) => () => {
        deleteBackend({
            projectName: paramProjectName,
            backends: [backendName],
        });
    };

    if (isLoadingPage)
        return (
            <Container>
                <Loader />
            </Container>
        );

    return (
        <>
            {data && backendsData && (
                <SpaceBetween size="l">
                    {backendsData.map((backend) => {
                        const isDisabledButtons = isDeleting && deleteArgs?.backends.includes(backend.name);

                        return (
                            <Container
                                key={backend.name}
                                header={
                                    <Header
                                        variant="h2"
                                        actions={
                                            <SpaceBetween direction="horizontal" size="s">
                                                <Button
                                                    disabled={isDisabledButtons}
                                                    onClick={() => goToBackendDetails(backend.name)}
                                                >
                                                    {t('common.edit')}
                                                </Button>

                                                <Button
                                                    disabled={isDisabledButtons}
                                                    onClick={getDeleteBackendAction(backend.name)}
                                                >
                                                    {t('common.delete')}
                                                </Button>
                                            </SpaceBetween>
                                        }
                                    >
                                        {backend.name}
                                    </Header>
                                }
                            >
                                {renderBackendDetails(backend)}
                            </Container>
                        );
                    })}

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
