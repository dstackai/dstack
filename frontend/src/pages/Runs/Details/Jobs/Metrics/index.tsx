import React, { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Box, ColumnLayout, Container, Header, LineChart } from 'components';

import { riseRouterException } from 'libs';
import { useGetRunQuery } from 'services/run';

import { bytesFormatter, formatPercent, formatTime } from './helpers';
import { useMetricsData } from './useMetricsData';

export const JobMetrics: React.FC = () => {
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

    const { cpuChartProps, memoryChartProps, eachGPUChartProps, eachGPUMemoryChartProps, isLoading } = useMetricsData({
        project_name: paramProjectName,
        run_name: runData?.run_spec.run_name ?? '',
        job_num: jobData?.job_spec.job_num ?? 0,
        limit: 1000,
    });

    const statusType = isLoading || isLoadingRun ? 'loading' : 'finished';

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
        <ColumnLayout columns={2}>
            <Container header={<Header variant="h2">{t('projects.run.metrics.cpu_utilization')}</Header>}>
                <LineChart
                    statusType={statusType}
                    series={cpuChartProps.series}
                    yTitle="Load"
                    {...defaultChartProps}
                    xDomain={cpuChartProps.xDomain}
                    yDomain={cpuChartProps.yDomain}
                    i18nStrings={{
                        xTickFormatter: formatTime,
                        yTickFormatter: formatPercent,
                    }}
                    hideFilter
                    hideLegend
                    xScaleType="time"
                />
            </Container>

            <Container header={<Header variant="h2">{t('projects.run.metrics.memory_used')}</Header>}>
                <LineChart
                    statusType={statusType}
                    series={memoryChartProps.series}
                    yTitle="Memory used"
                    {...defaultChartProps}
                    xDomain={memoryChartProps.xDomain}
                    yDomain={memoryChartProps.yDomain}
                    i18nStrings={{
                        xTickFormatter: formatTime,
                        yTickFormatter: bytesFormatter,
                    }}
                    hideFilter
                    hideLegend
                    xScaleType="time"
                />
            </Container>

            <Container header={<Header variant="h2">{t('projects.run.metrics.per_each_cpu_utilization')}</Header>}>
                <LineChart
                    statusType={statusType}
                    series={eachGPUChartProps.series}
                    yTitle="Load"
                    {...defaultChartProps}
                    xDomain={eachGPUChartProps.xDomain}
                    yDomain={eachGPUChartProps.yDomain}
                    i18nStrings={{
                        xTickFormatter: formatTime,
                        yTickFormatter: formatPercent,
                        filterPlaceholder: 'Filter data',
                    }}
                    xScaleType="time"
                />
            </Container>

            <Container header={<Header variant="h2">{t('projects.run.metrics.per_each_memory_used')}</Header>}>
                <LineChart
                    statusType={statusType}
                    series={eachGPUMemoryChartProps.series}
                    yTitle="Memory used"
                    {...defaultChartProps}
                    xDomain={eachGPUMemoryChartProps.xDomain}
                    yDomain={eachGPUMemoryChartProps.yDomain}
                    i18nStrings={{
                        xTickFormatter: formatTime,
                        yTickFormatter: bytesFormatter,
                        filterPlaceholder: 'Filter data',
                    }}
                    xScaleType="time"
                />
            </Container>
        </ColumnLayout>
    );
};
