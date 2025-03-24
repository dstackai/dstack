import { useMemo } from 'react';

import { useGetMetricsQuery } from 'services/run';

import { ALL_CPU_USAGE, ALL_MEMORY_USAGE, EACH_CPU_USAGE_PREFIX, EACH_MEMORY_USAGE_PREFIX } from './consts';
import { bytesFormatter, getChartProps } from './helpers';

export const useMetricsData = (params: TJobMetricsRequestParams) => {
    const { data: metricsData, isLoading } = useGetMetricsQuery(params, {
        skip: !params.run_name,
    });

    const totalCPUChartProps = useMemo(() => {
        const metricItem = metricsData?.metrics.find((i) => i.name === ALL_CPU_USAGE);

        return getChartProps({ metricItems: metricItem ? [metricItem] : [], renderTitle: () => 'Total CPU utilization %' });
    }, [metricsData]);

    const totalMemoryChartProps = useMemo(() => {
        const metricItem = metricsData?.metrics.find((i) => i.name === ALL_MEMORY_USAGE);

        return getChartProps({
            metricItems: metricItem ? [metricItem] : [],
            renderTitle: () => 'Total Memory Used',
            valueFormatter: bytesFormatter,
        });
    }, [metricsData]);

    const eachCPUChartProps = useMemo(() => {
        const metricItems = metricsData?.metrics.filter((i) => i.name.indexOf(EACH_CPU_USAGE_PREFIX) > -1) ?? [];

        return getChartProps({
            metricItems,
            renderTitle: (index) => `Total CPU utilization % GPU${index}`,
        });
    }, [metricsData]);

    const eachMemoryChartProps = useMemo(() => {
        const metricItems = metricsData?.metrics.filter((i) => i.name.indexOf(EACH_MEMORY_USAGE_PREFIX) > -1) ?? [];

        return getChartProps({
            metricItems,
            renderTitle: (index) => `Total Memory Used GPU${index}`,
            valueFormatter: bytesFormatter,
        });
    }, [metricsData]);

    return { totalCPUChartProps, eachCPUChartProps, totalMemoryChartProps, eachMemoryChartProps, isLoading };
};
