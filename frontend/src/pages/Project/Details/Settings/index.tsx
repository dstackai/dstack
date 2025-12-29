import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { debounce } from 'lodash';
import { ExpandableSection, Tabs } from '@cloudscape-design/components';
import Wizard from '@cloudscape-design/components/wizard';

import {
    Box,
    Button,
    ButtonWithConfirmation,
    Code,
    Container,
    Header,
    Hotspot,
    Loader,
    Popover,
    SelectCSD,
    SpaceBetween,
    StatusIndicator,
} from 'components';
import { HotspotIds } from 'layouts/AppLayout/TutorialPanel/constants';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { useCheckingForFleetsInProjects } from 'hooks/useCheckingForFleetsInProjectsOfMember';
import { riseRouterException } from 'libs';
import { copyToClipboard } from 'libs';
import { ROUTES } from 'routes';
import { useGetProjectQuery, useUpdateProjectMembersMutation, useUpdateProjectMutation } from 'services/project';
import { useGetRunsQuery } from 'services/run';
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

import styles from './styles.module.scss';

export const ProjectSettings: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const navigate = useNavigate();
    const paramProjectName = params.projectName ?? '';
    const [isExpandedCliSection, setIsExpandedCliSection] = React.useState(false);
    const [configCliCommand, copyCliCommand] = useConfigProjectCliCommand({ projectName: paramProjectName });

    const { isAvailableDeletingPermission, isProjectManager, isProjectAdmin, isAvailableProjectManaging } =
        useCheckAvailableProjectPermission();

    const [pushNotification] = useNotifications();
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

    useEffect(() => {
        setSelectedVisibility(data?.isPublic ? visibilityOptions[1] : visibilityOptions[0]);
    }, [data]);

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

    const [activeStepIndex, setActiveStepIndex] = React.useState(0);

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
                            <Wizard
                                i18nStrings={{
                                    stepNumberLabel: (stepNumber) => `Step ${stepNumber}`,
                                    collapsedStepsLabel: (stepNumber, stepsCount) => `Step ${stepNumber} of ${stepsCount}`,
                                    skipToButtonLabel: (step) => `Skip to ${step.title}`,
                                    navigationAriaLabel: 'Steps',
                                    // cancelButton: "Cancel",
                                    previousButton: 'Previous',
                                    nextButton: 'Next',
                                    optional: 'required',
                                }}
                                onNavigate={({ detail }) => setActiveStepIndex(detail.requestedStepIndex)}
                                activeStepIndex={activeStepIndex}
                                onSubmit={() => setIsExpandedCliSection(false)}
                                submitButtonText="Dismiss"
                                allowSkipTo={true}
                                steps={[
                                    {
                                        title: 'Install',
                                        // info: <InfoLink onFollow={() => openHelpPanel(CLI_INFO)} />,
                                        description: 'To use dstack, install the CLI on your local machine.',
                                        content: (
                                            <Hotspot hotspotId={HotspotIds.INSTALL_CLI_COMMAND}>
                                                <Tabs
                                                    variant="stacked"
                                                    tabs={[
                                                        {
                                                            label: 'uv',
                                                            id: 'uv',
                                                            content: (
                                                                <>
                                                                    <div className={styles.codeWrapper}>
                                                                        <Code className={styles.code}>
                                                                            uv tool install dstack -U
                                                                        </Code>

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
                                                                                        copyToClipboard(
                                                                                            'uv tool install dstack -U',
                                                                                        )
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
                                                                        <Code className={styles.code}>
                                                                            pip install dstack -U
                                                                        </Code>

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
                                            </Hotspot>
                                        ),
                                        isOptional: true,
                                    },
                                    {
                                        title: 'Add project',
                                        // info: <InfoLink onFollow={() => openHelpPanel(CLI_INFO)} />,
                                        description: 'To use dstack with this project, run the following command.',
                                        content: (
                                            <div className={styles.codeWrapper}>
                                                <Hotspot hotspotId={HotspotIds.CONFIGURE_CLI_COMMAND}>
                                                    <Code className={styles.code}>{configCliCommand}</Code>

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
                                                                onClick={copyCliCommand}
                                                            />
                                                        </Popover>
                                                    </div>
                                                </Hotspot>
                                            </div>
                                        ),
                                        isOptional: true,
                                    },
                                ]}
                            />
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
                                            {t('projects.edit.project_visibility')}
                                        </Box>

                                        <div>
                                            <ButtonWithConfirmation
                                                variant="danger-normal"
                                                disabled={!isProjectManager(data)}
                                                formAction="none"
                                                onClick={() => changeVisibilityHandler(selectedVisibility.value === 'public')}
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
