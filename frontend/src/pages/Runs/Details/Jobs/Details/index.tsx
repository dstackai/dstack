import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Box, ColumnLayout, Container, ContentLayout, DetailsHeader, Header, Loader, StatusIndicator, Tabs } from 'components';

import { useBreadcrumbs } from 'hooks';
import { riseRouterException } from 'libs';
import { getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';
import { useGetRunQuery } from 'services/run';

import { Logs } from '../../Logs';
import {
    getJobListItemBackend,
    getJobListItemInstance,
    getJobListItemPrice,
    getJobListItemRegion,
    getJobListItemResources,
    getJobListItemSpot,
    getJobStatus,
    getJobSubmittedAt,
    getJobTerminationReason,
} from '../List/helpers';
import { RunMetrics } from '../Metrics';

import styles from './styles.module.scss';

enum CodeTab {
    Details = 'details',
    Metrics = 'metrics',
}

const getJobSubmissionId = (job?: IJob): string | undefined => {
    if (!job) return;

    return job.job_submissions[job.job_submissions.length - 1]?.id;
};

export const JobDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const [codeTab, setCodeTab] = useState<CodeTab>(CodeTab.Details);
    const paramProjectName = params.projectName ?? '';
    const paramRunId = params.runId ?? '';
    const paramJobName = params.jobName ?? '';

    const {
        data: runData,
        isLoading: isLoadingRun,
        error: runError,
    } = useGetRunQuery({
        project_name: paramProjectName,
        id: paramRunId,
    });

    useEffect(() => {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        if (runError?.status === 404) {
            riseRouterException();
        }
    }, [runError]);

    const jobData = useMemo<IJob | null>(() => {
        if (!runData) return null;

        return runData.jobs.find((job) => job.job_spec.job_name === paramJobName) ?? null;
    }, [runData]);

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.FORMAT(paramProjectName),
        },
        {
            text: t('projects.runs'),
            href: ROUTES.RUNS.LIST,
        },
        {
            text: runData?.run_spec.run_name ?? '',
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRunId),
        },
        {
            text: t('projects.run.jobs'),
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRunId),
        },
        {
            text: paramJobName,
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.FORMAT(paramProjectName, paramRunId, paramJobName),
        },
    ]);

    return (
        <div className={styles.page}>
            <ContentLayout header={<DetailsHeader title={paramJobName} />}>
                {isLoadingRun && (
                    <Container>
                        <Loader />
                    </Container>
                )}

                {jobData && (
                    <>
                        <Tabs
                            onChange={({ detail }) => setCodeTab(detail.activeTabId as CodeTab)}
                            activeTabId={codeTab}
                            tabs={[
                                {
                                    label: 'Details',
                                    id: CodeTab.Details,
                                    content: (
                                        <div className={styles.details}>
                                            <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                                                <ColumnLayout columns={4} variant="text-grid">
                                                    <div>
                                                        <Box variant="awsui-key-label">{t('projects.run.submitted_at')}</Box>
                                                        <div>{getJobSubmittedAt(jobData)}</div>
                                                    </div>

                                                    <div>
                                                        <Box variant="awsui-key-label">{t('projects.run.status')}</Box>
                                                        <div>
                                                            <StatusIndicator type={getStatusIconType(getJobStatus(jobData))}>
                                                                {t(`projects.run.statuses.${getJobStatus(jobData)}`)}
                                                            </StatusIndicator>
                                                        </div>
                                                    </div>

                                                    <div>
                                                        <Box variant="awsui-key-label">
                                                            {t('projects.run.termination_reason')}
                                                        </Box>
                                                        <div>{getJobTerminationReason(jobData)}</div>
                                                    </div>

                                                    <div>
                                                        <Box variant="awsui-key-label">{t('projects.run.backend')}</Box>
                                                        <div>{getJobListItemBackend(jobData)}</div>
                                                    </div>

                                                    <div>
                                                        <Box variant="awsui-key-label">{t('projects.run.region')}</Box>
                                                        <div>{getJobListItemRegion(jobData)}</div>
                                                    </div>

                                                    <div>
                                                        <Box variant="awsui-key-label">{t('projects.run.instance')}</Box>
                                                        <div>{getJobListItemInstance(jobData)}</div>
                                                    </div>

                                                    <div>
                                                        <Box variant="awsui-key-label">{t('projects.run.resources')}</Box>
                                                        <div>{getJobListItemResources(jobData)}</div>
                                                    </div>

                                                    <div>
                                                        <Box variant="awsui-key-label">{t('projects.run.spot')}</Box>
                                                        <div>{getJobListItemSpot(jobData)}</div>
                                                    </div>

                                                    <div>
                                                        <Box variant="awsui-key-label">{t('projects.run.price')}</Box>
                                                        <div>{getJobListItemPrice(jobData)}</div>
                                                    </div>
                                                </ColumnLayout>
                                            </Container>

                                            <Logs
                                                projectName={paramProjectName}
                                                runName={runData?.run_spec?.run_name ?? ''}
                                                jobSubmissionId={getJobSubmissionId(jobData)}
                                                className={styles.logs}
                                            />
                                        </div>
                                    ),
                                },
                                {
                                    label: 'Metrics',
                                    id: CodeTab.Metrics,
                                    content: <RunMetrics />,
                                },
                            ]}
                        />
                    </>
                )}
            </ContentLayout>
        </div>
    );
};
