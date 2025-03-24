import type { LineChartProps } from '../../../../../components';
import { ALL_CPU_USAGE, GByte, kByte, MByte } from './consts';

export const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: 'numeric',
        hour12: !1,
    });
};

export const formatPercent = (percent: number) => `${percent} %`;

export const bytesFormatter = (bytes: number, hasPostfix = true) => {
    if (bytes >= GByte) {
        return (bytes / GByte).toFixed(1) + (hasPostfix ? ' GB' : '');
    }

    if (bytes >= MByte) {
        return (bytes / MByte).toFixed(1) + (hasPostfix ? ' MB' : '');
    }

    if (bytes >= kByte) {
        return (bytes / kByte).toFixed(1) + (hasPostfix ? ' KB' : '');
    }

    return bytes + (hasPostfix ? ' B' : '');
};

type GetSeriesDataArgs = {
    metricItem: IMetricsItem;
};

export const getSeriesData = ({ metricItem }: GetSeriesDataArgs) => {
    return metricItem.timestamps.map((time, index) => ({
        x: new Date(time),
        y: metricItem.values[index],
    }));
};

type GetChartPropsArgs = {
    renderTitle: (index: number) => string;
    type?: string;
    valueFormatter?: (value: number) => void;
    metricItems: IMetricsItem[];
};

export const getChartProps = ({ metricItems, renderTitle, type = 'line', valueFormatter }: GetChartPropsArgs) => {
    const series = metricItems.map((metricItem, index) => ({
        title: renderTitle(index),
        type,
        valueFormatter,
        data: getSeriesData({ metricItem }),
    }));

    const firstSeries = series?.[0]?.data;

    return {
        series,
        xDomain: [firstSeries?.[0]?.x, firstSeries?.[firstSeries.length - 1]?.x],
    };
};
