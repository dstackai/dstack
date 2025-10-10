import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { get as _get } from 'lodash';
import { format } from 'date-fns';

import { Box, ColumnLayout, Container, Header, Loader, NavigateLink, StatusIndicator } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { getRunError, getRunPriority, getRunStatusMessage, getStatusIconColor, getStatusIconType } from 'libs/run';
import { useGetRunQuery } from 'services/run';

import { finishedRunStatuses } from 'pages/Runs/constants';

import { ROUTES } from '../../../../routes';
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

    const status = finishedRunStatuses.includes(runData.status)
        ? (runData.latest_job_submission?.status ?? runData.status)
        : runData.status;
    const terminationReason = finishedRunStatuses.includes(runData.status)
        ? runData.latest_job_submission?.termination_reason
        : null;

    return (
        <>
            <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                <ColumnLayout columns={4} variant="text-grid">
                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.project')}</Box>

                        <div>
                            <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(runData.project_name)}>
                                {runData.project_name}
                            </NavigateLink>
                        </div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.repo')}</Box>

                        <div>
                            {_get(runData.run_spec.repo_data, 'repo_name', _get(runData.run_spec.repo_data, 'repo_dir', '-'))}
                        </div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.hub_user_name')}</Box>

                        <div>
                            <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(runData.user)}>{runData.user}</NavigateLink>
                        </div>
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
                        <Box variant="awsui-key-label">{t('projects.run.finished_at')}</Box>
                        <div>{runData.terminated_at ? format(new Date(runData.terminated_at), DATE_TIME_FORMAT) : '-'}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.status')}</Box>
                        <div>
                            <StatusIndicator
                                type={getStatusIconType(status, terminationReason)}
                                colorOverride={getStatusIconColor(status, terminationReason)}
                            >
                                {getRunStatusMessage(runData)}
                            </StatusIndicator>
                        </div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.error')}</Box>
                        <div>{getRunError(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.priority')}</Box>
                        <div>{getRunPriority(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.cost')}</Box>
                        <div>${runData.cost}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.price')}</Box>
                        <div>{getRunListItemPrice(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.resources')}</Box>
                        <div>{getRunListItemResources(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.region')}</Box>
                        <div>{getRunListItemRegion(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.instance_id')}</Box>
                        <div>{getRunListItemInstanceId(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.spot')}</Box>
                        <div>{getRunListItemSpot(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.backend')}</Box>
                        <div>{getRunListItemBackend(runData)}</div>
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

            {runData.jobs.length > 1 && (
                <JobList
                    projectName={paramProjectName}
                    runId={paramRunId}
                    jobs={runData.jobs}
                    runPriority={getRunPriority(runData)}
                />
            )}
        </>
    );
};
