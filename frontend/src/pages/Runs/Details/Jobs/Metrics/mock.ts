import { random } from 'lodash';

import { GByte, minute, startTime } from './consts';
import { bytesFormatter } from './helpers';

const getCPUSeries = () => ({
    title: 'Total CPU utilization %',
    type: 'line',
    data: new Array(60).fill(0).map((_, index) => ({ x: new Date(startTime + minute * index), y: random(0, 100) })),
});

const getMemorySeries = () => ({
    title: 'Total Memory Used',
    type: 'line',
    data: new Array(60).fill(0).map((_, index) => ({ x: new Date(startTime + minute * index), y: random(GByte, 128 * GByte) })),
    valueFormatter: bytesFormatter,
});

export const totalCPUSeries = [getCPUSeries()];

export const totalMemorySeries = [getMemorySeries(), { title: 'Total', type: 'threshold', y: 128 * GByte }];

export const eachCPUSeries = new Array(3).fill(0).map(getCPUSeries);

export const eachMemorySeries = [
    ...new Array(3).fill(0).map(getMemorySeries),
    { title: 'Total', type: 'threshold', y: 128 * GByte },
];
