import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Box, ColumnLayout, Container, Header, Loader, StatusIndicator } from 'components';

import { getStatusIconType } from 'libs/run';
import { useGetRunQuery } from 'services/run';

import { Logs } from '../../../Logs';
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
} from '../../List/helpers';

import styles from './styles.module.scss';

const getJobSubmissionId = (job?: IJob): string | undefined => {
    if (!job) return;

    return job.job_submissions[job.job_submissions.length - 1]?.id;
};

export const JobDetails = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunId = params.runId ?? '';
    const paramJobName = params.jobName ?? '';

    const { data: runData, isLoading: isLoadingRun } = useGetRunQuery({
        project_name: paramProjectName,
        id: paramRunId,
    });

    const jobData = useMemo<IJob | null>(() => {
        if (!runData) return null;

        return runData.jobs.find((job) => job.job_spec.job_name === paramJobName) ?? null;
    }, [runData]);

    if (isLoadingRun)
        return (
            <Container>
                <Loader />
            </Container>
        );

    if (!jobData) return null;

    return (
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
                runName={runData?.run_spec?.run_name ?? ''}
                jobSubmissionId={getJobSubmissionId(jobData)}
                className={styles.logs}
            />
        </div>
    );
};
