import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { debounce } from 'lodash';

import { Box, Button, Container, Header, Loader, Popover, SpaceBetween, StatusIndicator } from 'components';

import { useAppSelector, useBreadcrumbs, useNotifications } from 'hooks';
import { copyToClipboard } from 'libs';
import { ROUTES } from 'routes';
import { useDeleteProjectBackendMutation, useGetProjectBackendsQuery } from 'services/backend';
import { useGetProjectQuery, useUpdateProjectMembersMutation } from 'services/project';

import { selectAuthToken, selectUserData } from 'App/slice';

import { BackendsTable } from '../../Backends/Table';
import { ProjectMembers } from '../../Members';

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
    const [deleteBackend, { isLoading: isDeleting }] = useDeleteProjectBackendMutation();

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

    const goToBackendEdit = (backend: IProjectBackend) => {
        navigate(ROUTES.PROJECT.BACKEND.EDIT.FORMAT(paramProjectName, backend.name));
    };

    const deleteBackendHandler = (backends: readonly IProjectBackend[] | IProjectBackend[]) => {
        deleteBackend({
            projectName: paramProjectName,
            backends: backends.map((backend) => backend.name),
        });
    };

    const addBackendHandler = () => {
        navigate(ROUTES.PROJECT.BACKEND.ADD.FORMAT(paramProjectName));
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
                    <BackendsTable
                        backends={backendsData}
                        onClickAddBackend={addBackendHandler}
                        editBackend={goToBackendEdit}
                        deleteBackends={deleteBackendHandler}
                        isDisabledDelete={isDeleting}
                    />

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
