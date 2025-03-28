import { GByte, kByte, MByte } from './consts';

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
    yValueFormater?: (value: IMetricsItem['values'][number], index: number) => IMetricsItem['values'][number];
};

export const getSeriesData = ({ metricItem, yValueFormater = (value) => value }: GetSeriesDataArgs) => {
    return metricItem.timestamps.map((time, index) => ({
        x: new Date(time),
        y: yValueFormater(metricItem.values[index], index),
    }));
};

type GetChartPropsArgs = Pick<GetSeriesDataArgs, 'yValueFormater'> & {
    renderTitle: (index: number) => string;
    type?: string;
    valueFormatter?: (value: number) => void;
    metricItems: IMetricsItem[];
    customSeries?: unknown[];
    yDomain?: number[];
};

export const getChartProps = ({
    metricItems,
    renderTitle,
    type = 'line',
    valueFormatter,
    yValueFormater,
    customSeries = [],
    yDomain = [],
}: GetChartPropsArgs) => {
    const series = metricItems.map((metricItem, index) => ({
        title: renderTitle(index),
        type,
        valueFormatter,
        data: getSeriesData({ metricItem, yValueFormater }),
    }));

    const firstSeries = series?.[0]?.data;

    return {
        series: [...series, ...customSeries],
        xDomain: [firstSeries?.[0]?.x, firstSeries?.[firstSeries.length - 1]?.x],
        yDomain,
    };
};
