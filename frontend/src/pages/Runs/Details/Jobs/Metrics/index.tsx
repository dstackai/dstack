import React, { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Box, Container, ContentLayout, DetailsHeader, Header, LineChart, Loader, SpaceBetween } from 'components';

import { useBreadcrumbs } from 'hooks';
import { riseRouterException } from 'libs';
import { ROUTES } from 'routes';
import { useGetRunQuery } from 'services/run';

import { GByte } from './consts';
import { bytesFormatter, formatPercent, formatTime } from './helpers';
import { useMetricsData } from './useMetricsData';

export const RunMetrics: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
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

    const jobData = useMemo<IJob | null>(() => {
        if (!runData) return null;

        return runData.jobs.find((job) => job.job_spec.job_name === paramJobName) ?? null;
    }, [runData]);

    const { totalCPUChartProps, totalMemoryChartProps, eachCPUChartProps, eachMemoryChartProps, isLoading } = useMetricsData({
        project_name: paramProjectName,
        run_name: runData?.run_spec.run_name ?? '',
        job_num: jobData?.job_spec.job_num ?? 0,
        limit: 1000,
    });

    const statusType = isLoading || isLoadingRun ? 'loading' : 'finished';

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
        {
            text: t('projects.run.metrics.title'),
            href: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.METRICS.FORMAT(paramProjectName, paramRunId, paramJobName),
        },
    ]);

    useEffect(() => {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        if (runError?.status === 404) {
            riseRouterException();
        }
    }, [runError]);

    const defaultChartProps = {
        height: 300,
        xTitle: 'Time',
        empty: (
            <Box textAlign="center" color="inherit">
                <b>No data available</b>
                <Box variant="p" color="inherit">
                    There is no data available
                </Box>
            </Box>
        ),
        noMatch: (
            <Box textAlign="center" color="inherit">
                <b>No matching data</b>
                <Box variant="p" color="inherit">
                    There is no matching data to display
                </Box>
            </Box>
        ),
    };

    return (
        <ContentLayout
            header={<DetailsHeader title={`${t('projects.run.metrics.title')} ${runData?.run_spec.run_name ?? ''}`} />}
        >
            <SpaceBetween size="xxl" direction="vertical">
                <Container header={<Header variant="h2">{t('projects.run.metrics.cpu_utilization')}</Header>}>
                    <LineChart
                        statusType={statusType}
                        series={totalCPUChartProps.series}
                        yTitle="Load"
                        {...defaultChartProps}
                        xDomain={totalCPUChartProps.xDomain}
                        i18nStrings={{
                            xTickFormatter: formatTime,
                            yTickFormatter: formatPercent,
                        }}
                        yDomain={[0, 100]}
                        hideFilter
                        hideLegend
                        xScaleType="time"
                    />
                </Container>

                <Container header={<Header variant="h2">{t('projects.run.metrics.memory_used')}</Header>}>
                    <LineChart
                        statusType={statusType}
                        series={totalMemoryChartProps.series}
                        yTitle="Memory used"
                        {...defaultChartProps}
                        xDomain={totalMemoryChartProps.xDomain}
                        i18nStrings={{
                            xTickFormatter: formatTime,
                            yTickFormatter: bytesFormatter,
                        }}
                        yDomain={[0, 128 * GByte]}
                        hideFilter
                        hideLegend
                        xScaleType="time"
                    />
                </Container>

                <Container header={<Header variant="h2">{t('projects.run.metrics.per_each_cpu_utilization')}</Header>}>
                    <LineChart
                        statusType={statusType}
                        series={eachCPUChartProps.series}
                        yTitle="Load"
                        {...defaultChartProps}
                        xDomain={eachCPUChartProps.xDomain}
                        i18nStrings={{
                            xTickFormatter: formatTime,
                            yTickFormatter: formatPercent,
                            filterPlaceholder: 'Filter data',
                        }}
                        yDomain={[0, 100]}
                        xScaleType="time"
                    />
                </Container>

                <Container header={<Header variant="h2">{t('projects.run.metrics.per_each_memory_used')}</Header>}>
                    <LineChart
                        statusType={statusType}
                        series={eachMemoryChartProps.series}
                        yTitle="Memory used"
                        {...defaultChartProps}
                        xDomain={eachMemoryChartProps.xDomain}
                        i18nStrings={{
                            xTickFormatter: formatTime,
                            yTickFormatter: bytesFormatter,
                            filterPlaceholder: 'Filter data',
                        }}
                        yDomain={[0, 128 * GByte]}
                        xScaleType="time"
                    />
                </Container>
            </SpaceBetween>
        </ContentLayout>
    );
};
