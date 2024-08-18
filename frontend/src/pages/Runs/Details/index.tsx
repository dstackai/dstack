import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate, useParams } from 'react-router-dom';
import { get as _get } from 'lodash';
import { format } from 'date-fns';
import Button from '@cloudscape-design/components/button';

import { Box, Code, ColumnLayout, Container, ContentLayout, DetailsHeader, Header, Loader, StatusIndicator } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs, useNotifications } from 'hooks';
import { getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';
import { useDeleteRunsMutation, useGetRunQuery, useStopRunsMutation } from 'services/run';

import { riseRouterException } from '../../../libs';
import {
    getRunProvisioningData,
    isAvailableAbortingForRun,
    isAvailableDeletingForRun,
    isAvailableStoppingForRun,
} from '../utils';

import styles from './styles.module.scss';

export const RunDetails: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunName = params.runName ?? '';
    const [pushNotification] = useNotifications();

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
            text: paramRunName,
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRunName),
        },
    ]);

    const abortClickHandle = () => {
        stopRun({
            project_name: paramProjectName,
            runs_names: [paramRunName],
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
            project_name: paramProjectName,
            runs_names: [paramRunName],
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
            project_name: paramProjectName,
            runs_names: [paramRunName],
        })
            .unwrap()
            .then(() => {
                navigate(ROUTES.RUNS.LIST);
            })
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });
    };

    const isDisabledAbortButton = !runData || !isAvailableAbortingForRun(runData.status) || isStopping || isDeleting;
    const isDisabledStopButton = !runData || !isAvailableStoppingForRun(runData.status) || isStopping || isDeleting;
    const isDisabledDeleteButton = !runData || !isAvailableDeletingForRun(runData.status) || isStopping || isDeleting;
    const runProvisioningData = runData && getRunProvisioningData(runData);

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

                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.backend')}</Box>
                                <div>{runProvisioningData?.backend ?? '-'}</div>
                            </div>

                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.region')}</Box>
                                <div>{runProvisioningData?.region ?? '-'}</div>
                            </div>

                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.instance_id')}</Box>
                                <div>{runProvisioningData?.instance_id ?? '-'}</div>
                            </div>

                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.resources')}</Box>
                                <div>{runProvisioningData?.instance_type.resources.description}</div>
                            </div>

                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.spot')}</Box>
                                <div>{runProvisioningData?.instance_type.resources.spot.toString() ?? '-'}</div>
                            </div>

                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.price')}</Box>
                                <div>{runProvisioningData?.price ?? '-'}</div>
                            </div>

                            <div>
                                <Box variant="awsui-key-label">{t('projects.run.cost')}</Box>
                                <div>${runData.cost}</div>
                            </div>

                            {/*{runData.run_head.job_heads?.[0].error_code && (*/}
                            {/*    <div>*/}
                            {/*        <Box variant="awsui-key-label">{t('projects.run.error')}</Box>*/}
                            {/*        <div>{runData.run_head.job_heads?.[0].error_code}</div>*/}
                            {/*    </div>*/}
                            {/*)}*/}
                        </ColumnLayout>
                    </Container>
                )}

                <Outlet />
            </ContentLayout>
        </div>
    );
};
