import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { get as _get } from 'lodash';
import { format } from 'date-fns';
import Button from '@cloudscape-design/components/button';

import { Box, ColumnLayout, Container, ContentLayout, DetailsHeader, Header, Loader, StatusIndicator } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs, useNotifications } from 'hooks';
import { getServerError, riseRouterException } from 'libs';
import { getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';
import { useDeleteRunsMutation, useGetRunQuery, useStopRunsMutation } from 'services/run';

import { JobList } from './Jobs/List';
import { getJobSubmissionId } from './Logs/helpers';
import {
    getRunListItemBackend,
    getRunListItemInstanceId,
    getRunListItemPrice,
    getRunListItemRegion,
    getRunListItemResources,
    getRunListItemServiceUrl,
    getRunListItemSpot,
} from '../List/helpers';
import { isAvailableAbortingForRun, isAvailableDeletingForRun, isAvailableStoppingForRun } from '../utils';
import { Logs } from './Logs';

import styles from './styles.module.scss';

export const RunDetails: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunId = params.runId ?? '';
    const [pushNotification] = useNotifications();

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

    const [stopRun, { isLoading: isStopping }] = useStopRunsMutation();
    const [deleteRun, { isLoading: isDeleting }] = useDeleteRunsMutation();

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
            text: runData?.run_spec?.run_name ?? '',
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRunId),
        },
    ]);

    const abortClickHandle = () => {
        if (!runData) {
            return;
        }

        stopRun({
            project_name: paramProjectName,
            runs_names: [runData.run_spec.run_name],
            abort: true,
        })
            .unwrap()
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    };

    const stopClickHandle = () => {
        if (!runData) {
            return;
        }

        stopRun({
            project_name: paramProjectName,
            runs_names: [runData.run_spec.run_name],
            abort: false,
        })
            .unwrap()
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    };

    const deleteClickHandle = () => {
        if (!runData) {
            return;
        }

        deleteRun({
            project_name: paramProjectName,
            runs_names: [runData.run_spec.run_name],
        })
            .unwrap()
            .then(() => {
                navigate(ROUTES.RUNS.LIST);
            })
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    };

    const isDisabledAbortButton = !runData || !isAvailableAbortingForRun(runData.status) || isStopping || isDeleting;
    const isDisabledStopButton = !runData || !isAvailableStoppingForRun(runData.status) || isStopping || isDeleting;
    const isDisabledDeleteButton = !runData || !isAvailableDeletingForRun(runData.status) || isStopping || isDeleting;

    return (
        <div className={styles.page}>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={runData?.run_spec?.run_name ?? ''}
                        actionButtons={
                            <>
                                <Button onClick={abortClickHandle} disabled={isDisabledAbortButton}>
                                    {t('common.abort')}
                                </Button>

                                <Button onClick={stopClickHandle} disabled={isDisabledStopButton}>
                                    {t('common.stop')}
                                </Button>

                                {/*<Button onClick={deleteClickHandle} disabled={isDisabledDeleteButton}>*/}
                                {/*    {t('common.delete')}*/}
                                {/*</Button>*/}
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
                                        {_get(
                                            runData.run_spec.repo_data,
                                            'repo_name',
                                            _get(runData.run_spec.repo_data, 'repo_dir', '-'),
                                        )}
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

                            {getRunListItemServiceUrl(runData) && (
                                <ColumnLayout columns={1} variant="text-grid">
                                    <div>
                                        <Box variant="awsui-key-label">{t('projects.run.gateway')}</Box>
                                        <div>{getRunListItemServiceUrl(runData)}</div>
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

                        {runData.jobs.length > 1 && (
                            <JobList projectName={paramProjectName} runId={paramRunId} jobs={runData.jobs} />
                        )}
                    </>
                )}
            </ContentLayout>
        </div>
    );
};
