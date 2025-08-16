import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, /*useNavigate,*/ useParams } from 'react-router-dom';
import Button from '@cloudscape-design/components/button';

import { ContentLayout, DetailsHeader, Tabs } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { getServerError, riseRouterException } from 'libs';
import { ROUTES } from 'routes';
import { useDeleteRunsMutation, useGetRunQuery, useStopRunsMutation } from 'services/run';

import {
    isAvailableAbortingForRun,
    isAvailableStoppingForRun,
    // isAvailableDeletingForRun,
} from '../utils';

import styles from './styles.module.scss';

enum CodeTab {
    Details = 'details',
    Metrics = 'metrics',
    Logs = 'logs',
}

export const RunDetailsPage: React.FC = () => {
    const { t } = useTranslation();
    // const navigate = useNavigate();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunId = params.runId ?? '';
    const [pushNotification] = useNotifications();

    const {
        data: runData,
        error: runError,
        isLoading,
        refetch,
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
    const [, /* deleteRun ,*/ { isLoading: isDeleting }] = useDeleteRunsMutation();

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

    // const deleteClickHandle = () => {
    //     if (!runData) {
    //         return;
    //     }
    //
    //     deleteRun({
    //         project_name: paramProjectName,
    //         runs_names: [runData.run_spec.run_name],
    //     })
    //         .unwrap()
    //         .then(() => {
    //             navigate(ROUTES.RUNS.LIST);
    //         })
    //         .catch((error) => {
    //             pushNotification({
    //                 type: 'error',
    //                 content: t('common.server_error', { error: getServerError(error) }),
    //             });
    //         });
    // };

    const isDisabledAbortButton = !runData || !isAvailableAbortingForRun(runData.status) || isStopping || isDeleting;
    const isDisabledStopButton = !runData || !isAvailableStoppingForRun(runData.status) || isStopping || isDeleting;
    // const isDisabledDeleteButton = !runData || !isAvailableDeletingForRun(runData.status) || isStopping || isDeleting;

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

                                <Button
                                    iconName="refresh"
                                    disabled={isLoading}
                                    ariaLabel={t('common.refresh')}
                                    onClick={refetch}
                                />
                            </>
                        }
                    />
                }
            >
                <>
                    {runData?.jobs.length === 1 && (
                        <Tabs
                            withNavigation
                            tabs={[
                                {
                                    label: 'Details',
                                    id: CodeTab.Details,
                                    href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRunId),
                                },
                                {
                                    label: 'Logs',
                                    id: CodeTab.Logs,
                                    href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.LOGS.FORMAT(paramProjectName, paramRunId),
                                },
                                {
                                    label: 'Metrics',
                                    id: CodeTab.Metrics,
                                    href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.METRICS.FORMAT(paramProjectName, paramRunId),
                                },
                            ]}
                        />
                    )}

                    <Outlet />
                </>
            </ContentLayout>
        </div>
    );
};
