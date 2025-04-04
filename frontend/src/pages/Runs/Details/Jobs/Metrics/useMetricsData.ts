import { useMemo } from 'react';

import { useGetMetricsQuery } from 'services/run';

import {
    ALL_CPU_USAGE,
    CPU_NUMS,
    EACH_GPU_MEMORY_TOTAL,
    EACH_GPU_MEMORY_USAGE_PREFIX,
    EACH_GPU_USAGE_PREFIX,
    GByte,
    MEMORY_TOTAL,
    MEMORY_WORKING_SET,
} from './consts';
import { bytesFormatter, getChartProps } from './helpers';

export const useMetricsData = (params: TJobMetricsRequestParams) => {
    const { data: metricsData, isLoading } = useGetMetricsQuery(params, {
        skip: !params.run_name,
    });

    const cpuChartProps = useMemo(() => {
        const metricItem = metricsData?.find((i) => i.name === ALL_CPU_USAGE);
        const numsMetricItem = metricsData?.find((i) => i.name === CPU_NUMS);

        return getChartProps({
            metricItems: metricItem ? [metricItem] : [],
            renderTitle: () => 'CPU utilization %',
            yValueFormater: (value, index) => {
                return parseFloat((value / (numsMetricItem?.values?.[index] ?? 1)).toFixed(2));
            },
            yDomain: [0, 100],
        });
    }, [metricsData]);

    const memoryChartProps = useMemo(() => {
        const metricItem = metricsData?.find((i) => i.name === MEMORY_WORKING_SET);
        const totalMetricItem = metricsData?.find((i) => i.name === MEMORY_TOTAL);

        const totalMemory = totalMetricItem?.values[0];

        return getChartProps({
            metricItems: metricItem ? [metricItem] : [],
            renderTitle: () => 'Memory used',
            valueFormatter: bytesFormatter,
            customSeries: totalMetricItem?.values?.length
                ? [{ title: 'Memory total', type: 'threshold', valueFormatter: bytesFormatter, y: totalMemory }]
                : undefined,
            yDomain: [0, totalMemory ? totalMemory + GByte : 128 * GByte],
        });
    }, [metricsData]);

    const eachGPUChartProps = useMemo(() => {
        const metricItems = metricsData?.filter((i) => i.name.indexOf(EACH_GPU_USAGE_PREFIX) > -1) ?? [];

        return getChartProps({
            metricItems,
            renderTitle: (index) => `GPU utilization % GPU${index}`,
            yDomain: [0, 100],
        });
    }, [metricsData]);

    const eachGPUMemoryChartProps = useMemo(() => {
        const metricItems = metricsData?.filter((i) => i.name.indexOf(EACH_GPU_MEMORY_USAGE_PREFIX) > -1) ?? [];
        const totalMetricItem = metricsData?.find((i) => i.name === EACH_GPU_MEMORY_TOTAL);
        const totalMemory = totalMetricItem?.values[0];

        return getChartProps({
            metricItems,
            renderTitle: (index) => `Memory used GPU${index}`,
            valueFormatter: bytesFormatter,
            customSeries: totalMetricItem?.values?.length
                ? [{ title: 'Memory total', type: 'threshold', valueFormatter: bytesFormatter, y: totalMemory }]
                : undefined,
            yDomain: [0, totalMemory ? totalMemory + GByte : 128 * GByte],
        });
    }, [metricsData]);

    return { cpuChartProps, eachGPUChartProps, memoryChartProps, eachGPUMemoryChartProps, isLoading };
};
