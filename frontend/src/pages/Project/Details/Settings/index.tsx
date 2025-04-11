import React, { useCallback, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { debounce } from 'lodash';

import {
    Box,
    Button,
    ButtonWithConfirmation,
    Code,
    Container,
    Header,
    Hotspot,
    InfoLink,
    Loader,
    Popover,
    SelectCSD,
    SpaceBetween,
    StatusIndicator,
} from 'components';
import { HotspotIds } from 'layouts/AppLayout/TutorialPanel/constants';

import { useBreadcrumbs, useHelpPanel, useNotifications } from 'hooks';
import { riseRouterException } from 'libs';
import { ROUTES } from 'routes';
import { useGetProjectQuery, useUpdateProjectMembersMutation } from 'services/project';

import { useCheckAvailableProjectPermission } from 'pages/Project/hooks/useCheckAvailableProjectPermission';
import { useConfigProjectCliCommand } from 'pages/Project/hooks/useConfigProjectCliComand';
import { useDeleteProject } from 'pages/Project/hooks/useDeleteProject';
import { ProjectMembers } from 'pages/Project/Members';

import { useBackendsTable } from '../../Backends/hooks';
import { BackendsTable } from '../../Backends/Table';
import { GatewaysTable } from '../../Gateways';
import { useGatewaysTable } from '../../Gateways/hooks';
import { CLI_INFO } from './constants';

import styles from './styles.module.scss';

export const ProjectSettings: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const navigate = useNavigate();
    const paramProjectName = params.projectName ?? '';
    const [openHelpPanel] = useHelpPanel();
    const [configCliCommand, copyCliCommand] = useConfigProjectCliCommand({ projectName: paramProjectName });

    const { isAvailableDeletingPermission, isProjectManager, isProjectAdmin, isAvailableProjectManaging } =
        useCheckAvailableProjectPermission();

    const [pushNotification] = useNotifications();
    const [updateProjectMembers] = useUpdateProjectMembersMutation();
    const { deleteProject, isDeleting } = useDeleteProject();

    const { data, isLoading, error } = useGetProjectQuery({ name: paramProjectName });

    useEffect(() => {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        if (error?.status === 404) {
            riseRouterException();
        }
    }, [error]);

    const currentOwner = {
        label: data?.owner.username,
        value: data?.owner.username,
    };

    const {
        data: backendsData,
        isDeleting: isDeletingBackend,
        addBackend,
        deleteBackend,
        editBackend,
    } = useBackendsTable(paramProjectName, data?.backends ?? []);

    const { data: gatewaysData, isLoading: isLoadingGateways } = useGatewaysTable(paramProjectName);

    const isLoadingPage = isLoading || !data || isLoadingGateways;

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
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
            members: members.map((m) => ({ project_role: m.project_role, username: m.user.username })),
        })
            .unwrap()
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('projects.edit.update_members_success'),
                });
            })
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.data?.detail?.msg }),
                });
            });
    };

    const debouncedMembersHandler = useCallback(debounce(changeMembersHandler, 1000), []);

    const isDisabledButtons = useMemo<boolean>(() => {
        return isDeleting || !data || !isAvailableDeletingPermission(data);
    }, [data, isDeleting, isAvailableDeletingPermission]);

    const deleteProjectHandler = () => {
        if (!data) return;

        deleteProject(data).then(() => navigate(ROUTES.PROJECT.LIST));
    };

    if (isLoadingPage)
        return (
            <Container>
                <Loader />
            </Container>
        );

    return (
        <>
            {data && backendsData && gatewaysData && (
                <SpaceBetween size="l">
                    <Container
                        header={
                            <Header variant="h2" info={<InfoLink onFollow={() => openHelpPanel(CLI_INFO)} />}>
                                {t('projects.edit.cli')}
                            </Header>
                        }
                    >
                        <SpaceBetween size="s">
                            <Box variant="p" color="text-body-secondary">
                                Run the following commands to set up the CLI for this project
                            </Box>

                            <div className={styles.codeWrapper}>
                                <Hotspot hotspotId={HotspotIds.CONFIGURE_CLI_COMMAND}>
                                    <Code className={styles.code}>{configCliCommand}</Code>

                                    <div className={styles.copy}>
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
                                                onClick={copyCliCommand}
                                            />
                                        </Popover>
                                    </div>
                                </Hotspot>
                            </div>
                        </SpaceBetween>
                    </Container>

                    <BackendsTable
                        backends={backendsData}
                        {...(isProjectManager(data)
                            ? {
                                  onClickAddBackend: addBackend,
                                  editBackend: editBackend,
                                  deleteBackends: deleteBackend,
                                  isDisabledDelete: isDeletingBackend,
                              }
                            : {})}
                    />

                    <GatewaysTable gateways={gatewaysData} />

                    <ProjectMembers
                        onChange={debouncedMembersHandler}
                        members={data.members}
                        readonly={!isProjectManager(data)}
                        isAdmin={isProjectAdmin(data)}
                    />

                    <Container header={<Header variant="h2">{t('common.danger_zone')}</Header>}>
                        <SpaceBetween size="l">
                            <div className={styles.dangerSectionGrid}>
                                {isAvailableProjectManaging && (
                                    <>
                                        <Box variant="h5" color="text-body-secondary">
                                            {t('projects.edit.delete_this_project')}
                                        </Box>

                                        <div>
                                            <ButtonWithConfirmation
                                                variant="danger-normal"
                                                disabled={isDisabledButtons}
                                                formAction="none"
                                                onClick={deleteProjectHandler}
                                                confirmTitle={t('projects.edit.delete_project_confirm_title')}
                                                confirmContent={t('projects.edit.delete_project_confirm_message')}
                                            >
                                                {t('common.delete')}
                                            </ButtonWithConfirmation>
                                        </div>
                                    </>
                                )}

                                <Box variant="h5" color="text-body-secondary">
                                    {t('projects.edit.owner')}
                                </Box>

                                <div>
                                    <div className={styles.dangerSectionField}>
                                        <SelectCSD
                                            disabled
                                            options={[currentOwner]}
                                            selectedOption={currentOwner}
                                            expandToViewport={true}
                                            filteringType="auto"
                                        />
                                    </div>
                                </div>
                            </div>
                        </SpaceBetween>
                    </Container>
                </SpaceBetween>
            )}
        </>
    );
};
