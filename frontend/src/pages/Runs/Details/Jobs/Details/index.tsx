import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useParams } from 'react-router-dom';

import { ContentLayout, DetailsHeader, Tabs } from 'components';

import { useBreadcrumbs } from 'hooks';
import { riseRouterException } from 'libs';
import { ROUTES } from 'routes';
import { useGetRunQuery } from 'services/run';

import styles from './styles.module.scss';

enum CodeTab {
    Details = 'details',
    Metrics = 'metrics',
}

export const JobDetailsPage: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunId = params.runId ?? '';
    const paramJobName = params.jobName ?? '';

    const { data: runData, error: runError } = useGetRunQuery({
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
                <Tabs
                    withNavigation
                    tabs={[
                        {
                            label: 'Details',
                            id: CodeTab.Details,
                            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.FORMAT(
                                paramProjectName,
                                paramRunId,
                                paramJobName,
                            ),
                        },
                        {
                            label: 'Metrics',
                            id: CodeTab.Metrics,
                            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.METRICS.FORMAT(
                                paramProjectName,
                                paramRunId,
                                paramJobName,
                            ),
                        },
                    ]}
                />

                <Outlet />
            </ContentLayout>
        </div>
    );
};
