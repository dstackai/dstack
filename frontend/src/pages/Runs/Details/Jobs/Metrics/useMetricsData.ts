import { useMemo } from 'react';

import { useGetMetricsQuery } from 'services/run';

import {
    ALL_CPU_USAGE,
    ALL_MEMORY_USAGE,
    CPU_NUMS,
    EACH_CPU_USAGE_PREFIX,
    EACH_MEMORY_USAGE_PREFIX,
    GByte,
    TOTAL_MEMORY,
} from './consts';
import { bytesFormatter, getChartProps } from './helpers';

export const useMetricsData = (params: TJobMetricsRequestParams) => {
    const { data: metricsData, isLoading } = useGetMetricsQuery(params, {
        skip: !params.run_name,
    });

    const totalCPUChartProps = useMemo(() => {
        const metricItem = metricsData?.find((i) => i.name === ALL_CPU_USAGE);
        const numsMetricItem = metricsData?.find((i) => i.name === CPU_NUMS);

        return getChartProps({
            metricItems: metricItem ? [metricItem] : [],
            renderTitle: () => 'Total CPU utilization %',
            yValueFormater: (value, index) => {
                return parseFloat((value / (numsMetricItem?.values?.[index] ?? 1)).toFixed(2));
            },
            yDomain: [0, 100],
        });
    }, [metricsData]);

    const totalMemoryChartProps = useMemo(() => {
        const metricItem = metricsData?.find((i) => i.name === ALL_MEMORY_USAGE);
        const totalMetricItem = metricsData?.find((i) => i.name === TOTAL_MEMORY);

        const totalMemory = totalMetricItem?.values[0];

        return getChartProps({
            metricItems: metricItem ? [metricItem] : [],
            renderTitle: () => 'Total Memory Used',
            valueFormatter: bytesFormatter,
            customSeries: totalMetricItem?.values?.length
                ? [{ title: 'Total', type: 'threshold', valueFormatter: bytesFormatter, y: totalMemory }]
                : undefined,
            yDomain: [0, totalMemory ? totalMemory + GByte : 128 * GByte],
        });
    }, [metricsData]);

    const eachCPUChartProps = useMemo(() => {
        const metricItems = metricsData?.filter((i) => i.name.indexOf(EACH_CPU_USAGE_PREFIX) > -1) ?? [];

        return getChartProps({
            metricItems,
            renderTitle: (index) => `Total CPU utilization % GPU${index}`,
        });
    }, [metricsData]);

    const eachMemoryChartProps = useMemo(() => {
        const metricItems = metricsData?.filter((i) => i.name.indexOf(EACH_MEMORY_USAGE_PREFIX) > -1) ?? [];
        const totalMetricItem = metricsData?.find((i) => i.name === TOTAL_MEMORY);
        const totalMemory = totalMetricItem?.values[0];

        return getChartProps({
            metricItems,
            renderTitle: (index) => `Total Memory Used GPU${index}`,
            valueFormatter: bytesFormatter,
            customSeries: totalMetricItem?.values?.length ? [{ title: 'Total', type: 'threshold', y: totalMemory }] : undefined,
            yDomain: [0, totalMemory ? totalMemory + GByte : 128 * GByte],
        });
    }, [metricsData]);

    return { totalCPUChartProps, eachCPUChartProps, totalMemoryChartProps, eachMemoryChartProps, isLoading };
};
