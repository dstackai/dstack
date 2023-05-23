import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import Button from '@cloudscape-design/components/button';

import {
    Box,
    ColumnLayout,
    Container,
    ContentLayout,
    DetailsHeader,
    Header,
    Loader,
    StatusIndicator,
    Tabs,
    TabsProps,
} from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs, useNotifications } from 'hooks';
import { getRepoDisplayName } from 'libs/repo';
import { getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';
import { useGetProjectRepoQuery } from 'services/project';
import { useDeleteRunsMutation, useGetRunQuery, useStopRunsMutation } from 'services/run';

import { isAvailableAbortingForRun, isAvailableDeletingForRun, isAvailableStoppingForRun } from '../utils';

import styles from './styles.module.scss';

enum TabTypesEnum {
    LOGS = 'logs',
    ARTIFACTS = 'artifacts',
}

export const RunDetails: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { pathname } = useLocation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramRepoId = params.repoId ?? '';
    const paramRunName = params.runName ?? '';
    const [pushNotification] = useNotifications();

    const { data: repoData } = useGetProjectRepoQuery({
        name: paramProjectName,
        repo_id: paramRepoId,
    });

    const { data: runData, isLoading: isLoadingRun } = useGetRunQuery({
        name: paramProjectName,
        repo_id: paramRepoId,
        run_name: paramRunName,
    });

    const [stopRun, { isLoading: isStopping }] = useStopRunsMutation();
    const [deleteRun, { isLoading: isDeleting }] = useDeleteRunsMutation();

    const displayRepoName = repoData ? getRepoDisplayName(repoData) : 'Loading...';

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
            text: t('projects.repositories'),
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            text: displayRepoName,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(paramProjectName, paramRepoId),
        },
        {
            text: t('projects.runs'),
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(paramProjectName, paramRepoId),
        },
        {
            text: paramRunName,
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRepoId, paramRunName),
        },
    ]);

    const tabs: {
        label: string;
        id: TabTypesEnum;
        href: string;
    }[] = [
        {
            label: t('projects.run.log'),
            id: TabTypesEnum.LOGS,
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRepoId, paramRunName),
        },
        {
            label: t('projects.run.artifacts'),
            id: TabTypesEnum.ARTIFACTS,
            href: ROUTES.PROJECT.DETAILS.RUNS.ARTIFACTS.FORMAT(paramProjectName, paramRepoId, paramRunName),
        },
    ];

    const onChangeTab: TabsProps['onChange'] = ({ detail }) => {
        // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
        navigate(detail.activeTabHref!);
    };

    const activeTabId = useMemo(() => {
        const tab = tabs.find((t) => pathname === t.href);

        return tab?.id;
    }, [pathname]);

    const abortClickHandle = () => {
        stopRun({
            name: paramProjectName,
            repo_id: paramRepoId,
            run_names: [paramRunName],
            abort: true,
        })
            .unwrap()
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });
    };

    const stopClickHandle = () => {
        stopRun({
            name: paramProjectName,
            repo_id: paramRepoId,
            run_names: [paramRunName],
            abort: false,
        })
            .unwrap()
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });
    };

    const deleteClickHandle = () => {
        deleteRun({
            name: paramProjectName,
            repo_id: paramRepoId,
            run_names: [paramRunName],
        })
            .unwrap()
            .then(() => {
                navigate(ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(paramProjectName, paramRepoId));
            })
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });
    };

    const isDisabledAbortButton = !runData || !isAvailableAbortingForRun(runData) || isStopping || isDeleting;
    const isDisabledStopButton = !runData || !isAvailableStoppingForRun(runData) || isStopping || isDeleting;
    const isDisabledDeleteButton = !runData || !isAvailableDeletingForRun(runData) || isStopping || isDeleting;

    return (
        <div className={styles.page}>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={paramRunName}
                        actionButtons={
                            <>
                                <Button onClick={abortClickHandle} disabled={isDisabledAbortButton}>
                                    {t('common.abort')}
                                </Button>

                                <Button onClick={stopClickHandle} disabled={isDisabledStopButton}>
                                    {t('common.stop')}
                                </Button>

                                <Button onClick={deleteClickHandle} disabled={isDisabledDeleteButton}>
                                    {t('common.delete')}
                                </Button>
                            </>
                        }
                    />
                }
            >
                {isLoadingRun && (
                    <Container>
                        <Loader />
                    </Container>
                )}

                {runData && (
                    <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                        <ColumnLayout columns={4} variant="text-grid">
                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.workflow_name')}</Box>
                                <div>{runData.workflow_name ?? runData.provider_name}</div>
                            </div>

                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.status')}</Box>
                                <div>
                                    <StatusIndicator type={getStatusIconType(runData.status)}>
                                        {t(`projects.run.statuses.${runData.status}`)}
                                    </StatusIndicator>
                                </div>
                            </div>

                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.submitted_at')}</Box>
                                <div>{format(new Date(runData.submitted_at), DATE_TIME_FORMAT)}</div>
                            </div>

                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.artifacts_count')}</Box>
                                <div>{runData.artifact_heads?.length ?? 0}</div>
                            </div>
                        </ColumnLayout>
                    </Container>
                )}

                <Tabs onChange={onChangeTab} activeTabId={activeTabId} tabs={tabs} />

                <Outlet />
            </ContentLayout>
        </div>
    );
};
