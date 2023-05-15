import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { format } from 'date-fns';

import {
    Box,
    ColumnLayout,
    Container,
    ContentLayout,
    DetailsHeader,
    Header,
    Loader,
    SpaceBetween,
    StatusIndicator,
} from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs } from 'hooks';
import { getRepoDisplayName } from 'libs/repo';
import { getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';
import { useGetProjectRepoQuery } from 'services/project';
import { useGetRunQuery } from 'services/run';

import { Logs } from './Logs';

import styles from './styles.module.scss';

export const RunDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramRepoId = params.repoId ?? '';
    const paramRunName = params.runName ?? '';

    const { data: repoData } = useGetProjectRepoQuery({
        name: paramProjectName,
        repo_id: paramRepoId,
    });

    const { data: runData, isLoading: isLoadingRun } = useGetRunQuery({
        name: paramProjectName,
        repo_id: paramRepoId,
        run_name: paramRunName,
    });

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

    return (
        <div className={styles.page}>
            <ContentLayout header={<DetailsHeader title={paramRunName} />}>
                {isLoadingRun && !repoData && (
                    <Container>
                        <Loader />
                    </Container>
                )}

                {runData && (
                    <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                        <ColumnLayout columns={4} variant="text-grid">
                            <div>
                                <Box variant="awsui-key-label">
                                    {t('projects.run.workflow_name')}/{t('projects.run.provider_name')}
                                </Box>
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
                                <Box variant="awsui-key-label">{t('projects.run.artifacts')}</Box>
                                <div>{runData.artifact_heads?.length ?? 0}</div>
                            </div>
                        </ColumnLayout>
                    </Container>
                )}

                <Logs className={styles.logs} name={paramProjectName} repo_id={paramRepoId} run_name={paramRunName} />
            </ContentLayout>
        </div>
    );
};
