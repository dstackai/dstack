import { pick as _pick, sumBy as _sumBy, uniq as _uniq } from 'lodash';
import { add, format, parseISO, startOfMonth, sub } from 'date-fns';

import type { DateRangePickerProps, PropertyFilterProps } from 'components';

import { IModelExtended } from '../../List/types';

export type TMeteringPeriod = Extract<TMeteringGroupBy, 'day' | 'month'>;

export type TMeteringFilters = Pick<TMeteringListRequestParams, 'project_name' | 'user_name'>;

const DATE_FORMAT = 'yyyy-MM-dd';

export const DEFAULT_PERIOD: TMeteringPeriod = 'day';

const LAST_30_DAYS: DateRangePickerProps.RelativeOption = { key: 'last-30-days', amount: 30, unit: 'day', type: 'relative' };

const LAST_3_MONTHS: DateRangePickerProps.RelativeOption = { key: 'last-3-months', amount: 3, unit: 'month', type: 'relative' };

/**
 * By day, the time range picks days. By month, it picks months, which the picker does with its `month` granularity.
 * So each period has its own relative options and opens on its own time range.
 */
export const RELATIVE_OPTIONS: Record<TMeteringPeriod, DateRangePickerProps.RelativeOption[]> = {
    day: [{ key: 'last-7-days', amount: 7, unit: 'day', type: 'relative' }, LAST_30_DAYS, LAST_3_MONTHS],
    month: [
        LAST_3_MONTHS,
        { key: 'last-6-months', amount: 6, unit: 'month', type: 'relative' },
        { key: 'last-12-months', amount: 12, unit: 'month', type: 'relative' },
    ],
};

export const DEFAULT_TIME_RANGES: Record<TMeteringPeriod, DateRangePickerProps.Value> = {
    day: LAST_30_DAYS,
    month: LAST_3_MONTHS,
};

// From the start of the first day to the end of the last one. A relative time range ends today
const getDayBounds = (timeRange: DateRangePickerProps.Value, today: Date): [Date, Date] => {
    const [firstDay, lastDay] =
        timeRange.type === 'relative'
            ? [sub(today, { [`${timeRange.unit}s`]: timeRange.amount }), today]
            : [parseISO(timeRange.startDate), parseISO(timeRange.endDate)];

    return [firstDay, add(lastDay, { days: 1 })];
};

// Whole months. A relative time range is the running month and the months before it,
// so the last 3 months on 18 Nov are September, October and November.
// By month, the picker's units are months and years, and its absolute values are months, e.g. 2026-09
const getMonthBounds = (timeRange: DateRangePickerProps.Value, today: Date): [Date, Date] => {
    const thisMonth = startOfMonth(today);

    if (timeRange.type === 'relative') {
        const months = timeRange.unit === 'year' ? timeRange.amount * 12 : timeRange.amount;

        return [sub(thisMonth, { months: months - 1 }), add(thisMonth, { months: 1 })];
    }

    return [parseISO(`${timeRange.startDate}-01`), add(parseISO(`${timeRange.endDate}-01`), { months: 1 })];
};

/**
 * Metering sums tokens by UTC day, so a time range covers whole days, and by month whole months.
 */
const getTimeRangeBounds = (
    timeRange: DateRangePickerProps.Value,
    period: TMeteringPeriod,
    now: Date,
): Pick<TMeteringListRequestParams, 'start' | 'end'> => {
    const today = parseISO(now.toISOString().split('T')[0]);
    const [start, end] = period === 'month' ? getMonthBounds(timeRange, today) : getDayBounds(timeRange, today);

    return {
        start: `${format(start, DATE_FORMAT)}T00:00:00Z`,
        end: `${format(end, DATE_FORMAT)}T00:00:00Z`,
    };
};

type TMeteringRequest = {
    model: IModelExtended;
    timeRange: DateRangePickerProps.Value;
    period: TMeteringPeriod;
    filters: TMeteringFilters;
    now: Date;
};

/**
 * The table's rows: the model's tokens by day or month and by project. A filter by user narrows them to that user's requests.
 */
export const getMeteringRequestParams = ({
    model,
    timeRange,
    period,
    filters,
    now,
}: TMeteringRequest): TMeteringListRequestParams => ({
    ...getTimeRangeBounds(timeRange, period, now),
    group_by: [period, 'project'],
    model_project_name: model.project_name,
    model_name: model.name,
    ...filters,
});

/**
 * The rows don't have users, so the users that the filter offers come from a request of their own:
 * the same time range and model by user, in the project of the filter if it has one.
 */
export const getUserOptionsRequestParams = ({ filters, ...request }: TMeteringRequest): TMeteringListRequestParams => ({
    ...getMeteringRequestParams({ ...request, filters: _pick(filters, 'project_name') }),
    group_by: [request.period, 'user'],
});

/**
 * The API returns every row of a request, so the sum of the rows is the total.
 */
export const getMeteringTotal = (rows: IMeteringRow[]): IMeteringRow => ({
    input_tokens: _sumBy(rows, 'input_tokens'),
    cached_input_tokens: _sumBy(rows, 'cached_input_tokens'),
    output_tokens: _sumBy(rows, 'output_tokens'),
});

/**
 * Adds the projects and users of `rows` to the filter's `options`.
 */
export const getFilteringOptions = (
    rows: IMeteringRow[],
    options: PropertyFilterProps.FilteringOption[],
): PropertyFilterProps.FilteringOption[] =>
    (['project_name', 'user_name'] as const).flatMap((propertyKey) =>
        _uniq([
            ...options.filter((option) => option.propertyKey === propertyKey).map(({ value }) => value),
            ...rows.map((row) => row[propertyKey] ?? ''),
        ])
            .filter(Boolean)
            .sort()
            .map((value) => ({ propertyKey, value })),
    );

// A row has the day, or the first day of the month, that it sums
const getMeteringPeriod = (row: IMeteringRow) => row.day ?? row.month ?? '';

export const compareMeteringPeriods = (a: IMeteringRow, b: IMeteringRow) =>
    getMeteringPeriod(a).localeCompare(getMeteringPeriod(b));

export const formatMeteringPeriod = (row: IMeteringRow) => {
    if (row.day) {
        return format(parseISO(row.day), 'MM/dd/yyyy');
    }

    return row.month ? format(parseISO(row.month), 'MM/yyyy') : '';
};
