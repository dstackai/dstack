import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { get as _get } from 'lodash';
import { format } from 'date-fns';

import { Box, ColumnLayout, Container, Header, Loader, StatusIndicator } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { getStatusIconType } from 'libs/run';
import { useGetRunQuery } from 'services/run';

import {
    getRunListItemBackend,
    getRunListItemInstanceId,
    getRunListItemPrice,
    getRunListItemRegion,
    getRunListItemResources,
    getRunListItemServiceUrl,
    getRunListItemSpot,
} from '../../List/helpers';
import { JobList } from '../Jobs/List';
import { Logs } from '../Logs';
import { getJobSubmissionId } from '../Logs/helpers';

import styles from './styles.module.scss';

export const RunDetails = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunId = params.runId ?? '';

    const { data: runData, isLoading: isLoadingRun } = useGetRunQuery({
        project_name: paramProjectName,
        id: paramRunId,
    });

    const serviceUrl = runData ? getRunListItemServiceUrl(runData) : null;

    if (isLoadingRun)
        return (
            <Container>
                <Loader />
            </Container>
        );

    if (!runData) return null;

    return (
        <>
            <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                <ColumnLayout columns={4} variant="text-grid">
                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.project')}</Box>
                        <div>{runData.project_name}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.repo')}</Box>

                        <div>
                            {_get(runData.run_spec.repo_data, 'repo_name', _get(runData.run_spec.repo_data, 'repo_dir', '-'))}
                        </div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.hub_user_name')}</Box>
                        <div>{runData.user}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.configuration')}</Box>
                        <div>{runData.run_spec.configuration_path}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.submitted_at')}</Box>
                        <div>{format(new Date(runData.submitted_at), DATE_TIME_FORMAT)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.status')}</Box>
                        <div>
                            <StatusIndicator type={getStatusIconType(runData.status)}>
                                {t(`projects.run.statuses.${runData.status}`)}
                            </StatusIndicator>
                        </div>
                    </div>

                    {getRunListItemBackend(runData) && (
                        <div>
                            <Box variant="awsui-key-label">{t('projects.run.backend')}</Box>
                            <div>{getRunListItemBackend(runData)}</div>
                        </div>
                    )}

                    {getRunListItemRegion(runData) && (
                        <div>
                            <Box variant="awsui-key-label">{t('projects.run.region')}</Box>
                            <div>{getRunListItemRegion(runData)}</div>
                        </div>
                    )}

                    {getRunListItemInstanceId(runData) && (
                        <div>
                            <Box variant="awsui-key-label">{t('projects.run.instance_id')}</Box>
                            <div>{getRunListItemInstanceId(runData)}</div>
                        </div>
                    )}

                    {getRunListItemResources(runData) && (
                        <div>
                            <Box variant="awsui-key-label">{t('projects.run.resources')}</Box>
                            <div>{getRunListItemResources(runData)}</div>
                        </div>
                    )}

                    {getRunListItemSpot(runData) && (
                        <div>
                            <Box variant="awsui-key-label">{t('projects.run.spot')}</Box>
                            <div>{getRunListItemSpot(runData)}</div>
                        </div>
                    )}

                    {getRunListItemPrice(runData) && (
                        <div>
                            <Box variant="awsui-key-label">{t('projects.run.price')}</Box>
                            <div>{getRunListItemPrice(runData)}</div>
                        </div>
                    )}

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.cost')}</Box>
                        <div>${runData.cost}</div>
                    </div>
                </ColumnLayout>

                {serviceUrl && (
                    <ColumnLayout columns={1} variant="text-grid">
                        <div>
                            <Box variant="awsui-key-label">{t('projects.run.service_url')}</Box>
                            <div>
                                <a href={serviceUrl}>{serviceUrl}</a>
                            </div>
                        </div>
                    </ColumnLayout>
                )}
            </Container>

            {runData.jobs.length === 1 && (
                <Logs
                    projectName={paramProjectName}
                    runName={runData?.run_spec?.run_name ?? ''}
                    jobSubmissionId={getJobSubmissionId(runData)}
                    className={styles.logs}
                />
            )}

            {runData.jobs.length > 1 && <JobList projectName={paramProjectName} runId={paramRunId} jobs={runData.jobs} />}
        </>
    );
};
