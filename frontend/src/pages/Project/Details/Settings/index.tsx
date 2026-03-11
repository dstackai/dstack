import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useDispatch } from 'react-redux';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { debounce } from 'lodash';
import { ExpandableSection, Tabs } from '@cloudscape-design/components';
import { FetchBaseQueryError } from '@reduxjs/toolkit/query';

import {
    Box,
    Button,
    ButtonWithConfirmation,
    Code,
    ConfirmationDialog,
    Container,
    FormField,
    Header,
    Hotspot,
    InfoLink,
    InputCSD,
    Loader,
    Popover,
    SelectCSD,
    SpaceBetween,
    StatusIndicator,
} from 'components';
import { HotspotIds } from 'layouts/AppLayout/TutorialPanel/constants';

import { useBreadcrumbs, useHelpPanel, useNotifications } from 'hooks';
import { useCheckingForFleetsInProjects } from 'hooks/useCheckingForFleetsInProjectsOfMember';
import { riseRouterException } from 'libs';
import { copyToClipboard } from 'libs';
import { ROUTES } from 'routes';
import { useGetProjectQuery, useUpdateProjectMembersMutation, useUpdateProjectMutation } from 'services/project';
import { useGetRunsQuery } from 'services/run';
import { templateApi } from 'services/templates';
import { useGetUserDataQuery } from 'services/user';

import { useCheckAvailableProjectPermission } from 'pages/Project/hooks/useCheckAvailableProjectPermission';
import { useConfigProjectCliCommand } from 'pages/Project/hooks/useConfigProjectCliComand';
import { useDeleteProject } from 'pages/Project/hooks/useDeleteProject';
import { ProjectMembers } from 'pages/Project/Members';
import { getProjectRoleByUserName } from 'pages/Project/utils';

import { useBackendsTable } from '../../Backends/hooks';
import { BackendsTable } from '../../Backends/Table';
import { NoFleetProjectAlert } from '../../components/NoFleetProjectAlert';
import { GatewaysTable } from '../../Gateways';
import { useGatewaysTable } from '../../Gateways/hooks';
import { ProjectSecrets } from '../../Secrets';
import { TEMPLATES_REPO_INFO } from './constants';

import styles from './styles.module.scss';

type ApiErrorResponse = { detail?: string | { msg?: string } | Array<{ msg?: string }> };

const isFetchBaseQueryError = (error: unknown): error is FetchBaseQueryError =>
    typeof error === 'object' && error !== null && 'status' in error;

export const ProjectSettings: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const navigate = useNavigate();
    const location = useLocation();
    const paramProjectName = params.projectName ?? '';
    const [isExpandedCliSection, setIsExpandedCliSection] = React.useState(false);
    const [configCliCommand, copyCliCommand] = useConfigProjectCliCommand({ projectName: paramProjectName });

    const { isAvailableDeletingPermission, isProjectManager, isProjectAdmin, isAvailableProjectManaging } =
        useCheckAvailableProjectPermission();

    const [pushNotification] = useNotifications();
    const [openHelpPanel] = useHelpPanel();
    const dispatch = useDispatch();
    const [updateProjectMembers] = useUpdateProjectMembersMutation();
    const [updateProject] = useUpdateProjectMutation();
    const { deleteProject, isDeleting } = useDeleteProject();
    const { data: currentUser } = useGetUserDataQuery({});

    const projectNames = useMemo(() => [paramProjectName], [paramProjectName]);

    const projectHavingFleetMap = useCheckingForFleetsInProjects({ projectNames });

    const { data, isLoading, error } = useGetProjectQuery({ name: paramProjectName });

    const { data: runsData } = useGetRunsQuery({
        project_name: paramProjectName,
        limit: 1,
    });

    useEffect(() => {
        setIsExpandedCliSection(!runsData || runsData.length === 0);
    }, [runsData]);

    useEffect(() => {
        if (error && 'status' in error && error.status === 404) {
            riseRouterException();
        }
    }, [error]);

    const currentUserRole = data ? getProjectRoleByUserName(data, currentUser?.username ?? '') : null;
    const isProjectMember = currentUserRole !== null;

    const currentOwner = {
        label: data?.owner.username,
        value: data?.owner.username,
    };

    const visibilityOptions = [
        { label: t('projects.edit.visibility.private') || '', value: 'private' },
        { label: t('projects.edit.visibility.public') || '', value: 'public' },
    ];

    const [selectedVisibility, setSelectedVisibility] = useState(data?.isPublic ? visibilityOptions[1] : visibilityOptions[0]);
    const [templatesRepoValue, setTemplatesRepoValue] = useState<string>('');
    const [templatesRepoError, setTemplatesRepoError] = useState<string | null>(null);
    const [isChangeTemplatesRepoVisible, setIsChangeTemplatesRepoVisible] = useState(false);
    const [isResetTemplatesRepoVisible, setIsResetTemplatesRepoVisible] = useState(false);
    const changeTemplatesRepoInputWrapperRef = React.useRef<HTMLDivElement | null>(null);
    const dangerZoneRef = React.useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        setSelectedVisibility(data?.isPublic ? visibilityOptions[1] : visibilityOptions[0]);
    }, [data]);

    useEffect(() => {
        setTemplatesRepoValue(data?.templates_repo ?? '');
    }, [data?.templates_repo]);

    useEffect(() => {
        if (!isChangeTemplatesRepoVisible) {
            return;
        }
        const timer = setTimeout(() => {
            changeTemplatesRepoInputWrapperRef.current?.querySelector('input')?.focus();
        }, 10);
        return () => clearTimeout(timer);
    }, [isChangeTemplatesRepoVisible]);

    const {
        data: backendsData,
        isDeleting: isDeletingBackend,
        addBackend,
        deleteBackend,
        editBackend,
    } = useBackendsTable(paramProjectName, data?.backends ?? []);

    const { data: gatewaysData, isLoading: isLoadingGateways } = useGatewaysTable(paramProjectName);

    const isLoadingPage = isLoading || !data || isLoadingGateways;

    useEffect(() => {
        if (location.hash === '#danger-zone') {
            setTimeout(() => {
                dangerZoneRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 0);
        }
    }, [location.hash, isLoadingPage]);

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
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            .catch((error: any) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.data?.detail?.msg }),
                });
            });
    };

    const debouncedMembersHandler = useCallback(debounce(changeMembersHandler, 1000), []);

    const changeVisibilityHandler = (is_public: boolean) => {
        updateProject({
            project_name: paramProjectName,
            is_public: is_public,
        })
            .unwrap()
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('projects.edit.update_visibility_success'),
                });
            })
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            .catch((error: any) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.data?.detail?.msg }),
                });
            });
    };

    const getApiErrorMessage = (error: unknown): string => {
        const detail = isFetchBaseQueryError(error) ? (error.data as ApiErrorResponse | undefined)?.detail : undefined;
        if (Array.isArray(detail)) {
            return detail[0]?.msg ?? t('common.server_error', { error: 'Unknown error' });
        }
        if (typeof detail === 'string') {
            return detail;
        }
        if (detail?.msg) {
            return detail.msg;
        }
        return t('common.server_error', { error: 'Unknown error' });
    };

    const updateTemplatesRepoHandler = async (): Promise<boolean> => {
        const templates_repo = templatesRepoValue.trim() === '' ? null : templatesRepoValue.trim();
        try {
            await updateProject({
                project_name: paramProjectName,
                templates_repo,
            }).unwrap();
            dispatch(templateApi.util.invalidateTags(['Templates']));
            pushNotification({
                type: 'success',
                content: t('projects.edit.update_templates_repo_success'),
            });
            return true;
        } catch (error: unknown) {
            const errorMessage = getApiErrorMessage(error);
            setTemplatesRepoError(errorMessage);
            return false;
        }
    };

    const openChangeTemplatesRepoDialog = () => {
        setTemplatesRepoValue(data?.templates_repo ?? '');
        setTemplatesRepoError(null);
        setIsChangeTemplatesRepoVisible(true);
    };

    const closeChangeTemplatesRepoDialog = () => {
        setTemplatesRepoError(null);
        setIsChangeTemplatesRepoVisible(false);
    };

    const openResetTemplatesRepoDialog = () => {
        setIsResetTemplatesRepoVisible(true);
    };

    const closeResetTemplatesRepoDialog = () => {
        setIsResetTemplatesRepoVisible(false);
    };

    const confirmChangeTemplatesRepo = async () => {
        if (templatesRepoValue.trim() === '') {
            setTemplatesRepoError(t('projects.edit.templates_repo_required'));
            return;
        }
        const isUpdated = await updateTemplatesRepoHandler();
        if (isUpdated) {
            closeChangeTemplatesRepoDialog();
        }
    };

    const confirmResetTemplatesRepo = () => {
        setTemplatesRepoValue('');
        updateProject({
            project_name: paramProjectName,
            reset_templates_repo: true,
        })
            .unwrap()
            .then(() => {
                dispatch(templateApi.util.invalidateTags(['Templates']));
                pushNotification({
                    type: 'success',
                    content: t('projects.edit.update_templates_repo_success'),
                });
            })
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            .catch((error: any) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.data?.detail?.msg }),
                });
            });
        closeResetTemplatesRepoDialog();
    };

    const isDisabledButtons = useMemo<boolean>(() => {
        return isDeleting || !data || !isAvailableDeletingPermission(data);
    }, [data, isDeleting, isAvailableDeletingPermission]);

    const deleteProjectHandler = () => {
        if (!data) return;

        deleteProject(data)
            .then(() => navigate(ROUTES.PROJECT.LIST))
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            .catch((error: any) => {
                console.error('Delete project failed:', error);
            });
    };

    const projectDontHasFleet = !projectHavingFleetMap?.[paramProjectName];

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
                    <NoFleetProjectAlert projectName={paramProjectName} show={projectDontHasFleet} dismissible />

                    {isProjectMember && (
                        <ExpandableSection
                            variant="container"
                            headerText="CLI"
                            expanded={isExpandedCliSection}
                            onChange={({ detail }) => setIsExpandedCliSection(detail.expanded)}
                            headerActions={
                                <Button
                                    iconName="script"
                                    variant={isExpandedCliSection ? 'normal' : 'primary'}
                                    onClick={() => setIsExpandedCliSection((prev) => !prev)}
                                />
                            }
                            // headerInfo={<InfoLink onFollow={() => openHelpPanel(CLI_INFO)} />}
                        >
                            <SpaceBetween size="s">
                                <Box>To use dstack with this project, run the following command.</Box>

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

                                <ExpandableSection headerText="No CLI installed?">
                                    <SpaceBetween size="s">
                                        <Box />
                                        <Box>To use dstack, install the CLI on your local machine.</Box>

                                        <Tabs
                                            variant="container"
                                            tabs={[
                                                {
                                                    label: 'uv',
                                                    id: 'uv',
                                                    content: (
                                                        <>
                                                            <div className={styles.codeWrapper}>
                                                                <Code className={styles.code}>uv tool install dstack -U</Code>

                                                                <div className={styles.copy}>
                                                                    <Popover
                                                                        dismissButton={false}
                                                                        position="top"
                                                                        size="small"
                                                                        triggerType="custom"
                                                                        content={
                                                                            <StatusIndicator type="success">
                                                                                {t('common.copied')}
                                                                            </StatusIndicator>
                                                                        }
                                                                    >
                                                                        <Button
                                                                            formAction="none"
                                                                            iconName="copy"
                                                                            variant="normal"
                                                                            onClick={() =>
                                                                                copyToClipboard('uv tool install dstack -U')
                                                                            }
                                                                        />
                                                                    </Popover>
                                                                </div>
                                                            </div>
                                                        </>
                                                    ),
                                                },
                                                {
                                                    label: 'pip',
                                                    id: 'pip',
                                                    content: (
                                                        <>
                                                            <div className={styles.codeWrapper}>
                                                                <Code className={styles.code}>pip install dstack -U</Code>

                                                                <div className={styles.copy}>
                                                                    <Popover
                                                                        dismissButton={false}
                                                                        position="top"
                                                                        size="small"
                                                                        triggerType="custom"
                                                                        content={
                                                                            <StatusIndicator type="success">
                                                                                {t('common.copied')}
                                                                            </StatusIndicator>
                                                                        }
                                                                    >
                                                                        <Button
                                                                            formAction="none"
                                                                            iconName="copy"
                                                                            variant="normal"
                                                                            onClick={() =>
                                                                                copyToClipboard('pip install dstack -U')
                                                                            }
                                                                        />
                                                                    </Popover>
                                                                </div>
                                                            </div>
                                                        </>
                                                    ),
                                                },
                                            ]}
                                        />
                                    </SpaceBetween>
                                </ExpandableSection>
                            </SpaceBetween>
                        </ExpandableSection>
                    )}

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
                        project={data}
                    />

                    <ProjectSecrets project={data} />

                    <div id="danger-zone" ref={dangerZoneRef}>
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

                                    {isAvailableProjectManaging && (
                                        <>
                                            <Box variant="h5" color="text-body-secondary">
                                                {t('projects.edit.project_visibility_settings')}
                                            </Box>

                                            <div>
                                                <ButtonWithConfirmation
                                                    variant="danger-normal"
                                                    disabled={!isProjectAdmin(data)}
                                                    formAction="none"
                                                    onClick={() =>
                                                        changeVisibilityHandler(selectedVisibility.value === 'public')
                                                    }
                                                    confirmTitle={t('projects.edit.update_visibility_confirm_title')}
                                                    confirmButtonLabel={t('projects.edit.change_visibility')}
                                                    confirmContent={
                                                        <SpaceBetween size="s">
                                                            <Box variant="p" color="text-body-secondary">
                                                                {t('projects.edit.update_visibility_confirm_message')}
                                                            </Box>
                                                            <div className={styles.dangerSectionField}>
                                                                <SelectCSD
                                                                    options={visibilityOptions}
                                                                    selectedOption={selectedVisibility}
                                                                    onChange={(event) =>
                                                                        setSelectedVisibility(
                                                                            event.detail.selectedOption as {
                                                                                label: string;
                                                                                value: string;
                                                                            },
                                                                        )
                                                                    }
                                                                    expandToViewport={true}
                                                                    filteringType="auto"
                                                                />
                                                            </div>
                                                        </SpaceBetween>
                                                    }
                                                >
                                                    {t('projects.edit.change_visibility')}
                                                </ButtonWithConfirmation>
                                            </div>
                                        </>
                                    )}

                                    <Box variant="h5" color="text-body-secondary">
                                        {t('projects.edit.transfer_ownership')}
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

                                    {isAvailableProjectManaging && (
                                        <>
                                            <div className={styles.templatesRepoTitle}>
                                                <Box variant="h5" color="text-body-secondary">
                                                    {t('projects.edit.override_project_templates')}
                                                </Box>
                                                <InfoLink onFollow={() => openHelpPanel(TEMPLATES_REPO_INFO)} />
                                            </div>

                                            <div className={styles.templatesRepoRow}>
                                                {data.templates_repo && (
                                                    <InputCSD
                                                        value={data.templates_repo}
                                                        disabled
                                                        className={styles.templatesRepoInput}
                                                    />
                                                )}
                                                <SpaceBetween
                                                    direction="horizontal"
                                                    size="xs"
                                                    className={styles.templatesRepoActions}
                                                >
                                                    <Button
                                                        onClick={openChangeTemplatesRepoDialog}
                                                        disabled={!isProjectAdmin(data)}
                                                    >
                                                        {data.templates_repo
                                                            ? t('projects.edit.change_visibility')
                                                            : t('projects.edit.configure_templates_repo')}
                                                    </Button>
                                                    <Button
                                                        variant="danger-normal"
                                                        onClick={openResetTemplatesRepoDialog}
                                                        disabled={!isProjectAdmin(data) || !data.templates_repo}
                                                    >
                                                        {t('projects.edit.reset_templates_repo')}
                                                    </Button>
                                                </SpaceBetween>
                                            </div>
                                        </>
                                    )}
                                </div>
                            </SpaceBetween>
                        </Container>
                    </div>
                </SpaceBetween>
            )}

            <ConfirmationDialog
                visible={isChangeTemplatesRepoVisible}
                onDiscard={closeChangeTemplatesRepoDialog}
                onConfirm={confirmChangeTemplatesRepo}
                title={t('projects.edit.change_templates_repo_title')}
                confirmButtonLabel={t('projects.edit.save_templates_repo')}
                content={
                    <SpaceBetween size="s">
                        <Box variant="p" color="text-body-secondary">
                            {t('projects.edit.change_templates_repo_message')}
                        </Box>
                        <div ref={changeTemplatesRepoInputWrapperRef}>
                            <FormField errorText={templatesRepoError ?? undefined}>
                                <InputCSD
                                    value={templatesRepoValue}
                                    onChange={({ detail }) => {
                                        setTemplatesRepoValue(detail.value);
                                        if (templatesRepoError) {
                                            setTemplatesRepoError(null);
                                        }
                                    }}
                                    onKeyDown={({ detail }) => {
                                        if (detail.key === 'Enter') {
                                            void confirmChangeTemplatesRepo();
                                        }
                                    }}
                                    placeholder={t('projects.edit.templates_repo_placeholder')}
                                />
                            </FormField>
                        </div>
                    </SpaceBetween>
                }
            />

            <ConfirmationDialog
                visible={isResetTemplatesRepoVisible}
                onDiscard={closeResetTemplatesRepoDialog}
                onConfirm={confirmResetTemplatesRepo}
                title={t('projects.edit.reset_templates_repo_title')}
                confirmButtonLabel={t('projects.edit.reset_templates_repo')}
                content={<Box variant="p">{t('projects.edit.reset_templates_repo_message')}</Box>}
            />
        </>
    );
};
