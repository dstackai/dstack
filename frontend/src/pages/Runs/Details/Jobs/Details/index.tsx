import React, { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Box, ColumnLayout, Container, ContentLayout, DetailsHeader, Header, Loader, StatusIndicator } from 'components';

import { useBreadcrumbs } from 'hooks';
import { riseRouterException } from 'libs';
import { ROUTES } from 'routes';
import { useGetRunQuery } from 'services/run';

import { getStatusIconType } from '../../../../../libs/run';
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

import styles from './styles.module.scss';

const getJobSubmissionId = (job?: IJob): string | undefined => {
    if (!job) return;

    return job.job_submissions[job.job_submissions.length - 1]?.id;
};

export const JobDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunName = params.runName ?? '';
    const paramJobName = params.jobName ?? '';

    const {
        data: runData,
        isLoading: isLoadingRun,
        error: runError,
    } = useGetRunQuery({
        project_name: paramProjectName,
        run_name: paramRunName,
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
            text: paramRunName,
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRunName),
        },
        {
            text: t('projects.run.jobs'),
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRunName),
        },
        {
            text: paramJobName,
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.FORMAT(paramProjectName, paramRunName, paramJobName),
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
                                    <Box variant="awsui-key-label">{t('projects.run.termination_reason')}</Box>
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
                            runName={paramRunName}
                            jobSubmissionId={getJobSubmissionId(jobData)}
                            className={styles.logs}
                        />
                    </>
                )}
            </ContentLayout>
        </div>
    );
};
