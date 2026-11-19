import { pick as _pick, sumBy as _sumBy, uniq as _uniq } from 'lodash';
import { add, format, parseISO, startOfMonth, sub } from 'date-fns';

import type { DateRangePickerProps, PropertyFilterProps } from 'components';

import { IModelExtended } from '../../List/types';

export type TUsagePeriod = Extract<TMeteringGroupBy, 'day' | 'month'>;

export type TUsageFilters = Pick<TMeteringListRequestParams, 'project_name' | 'user_name'>;

const DATE_FORMAT = 'yyyy-MM-dd';

export const DEFAULT_TIME_RANGE: DateRangePickerProps.RelativeOption = {
    key: 'last-3-months',
    amount: 3,
    unit: 'month',
    type: 'relative',
};

export const relativeOptions: DateRangePickerProps.RelativeOption[] = [
    { key: 'last-7-days', amount: 7, unit: 'day', type: 'relative' },
    { key: 'last-30-days', amount: 30, unit: 'day', type: 'relative' },
    DEFAULT_TIME_RANGE,
];

/**
 * Metering sums tokens by UTC day, so a time range covers whole days:
 * from the start of its first day to the end of its last one. A relative time range ends today.
 * By month, it covers whole months: from the start of the month of its first day to the end of the month of its last one.
 */
const getTimeRangeBounds = (
    timeRange: DateRangePickerProps.Value,
    period: TUsagePeriod,
    now: Date,
): Pick<TMeteringListRequestParams, 'start' | 'end'> => {
    const today = parseISO(now.toISOString().split('T')[0]);

    const [firstDay, lastDay] =
        timeRange.type === 'relative'
            ? [sub(today, { [`${timeRange.unit}s`]: timeRange.amount }), today]
            : [parseISO(timeRange.startDate), parseISO(timeRange.endDate)];

    const [start, end] =
        period === 'month'
            ? [startOfMonth(firstDay), add(startOfMonth(lastDay), { months: 1 })]
            : [firstDay, add(lastDay, { days: 1 })];

    return {
        start: `${format(start, DATE_FORMAT)}T00:00:00Z`,
        end: `${format(end, DATE_FORMAT)}T00:00:00Z`,
    };
};

type TUsageRequest = {
    model: IModelExtended;
    timeRange: DateRangePickerProps.Value;
    period: TUsagePeriod;
    filters: TUsageFilters;
    now: Date;
};

/**
 * The table's rows: the model's tokens by day or month and by project. A filter by user narrows them to that user's requests.
 */
export const getUsageRequestParams = ({
    model,
    timeRange,
    period,
    filters,
    now,
}: TUsageRequest): TMeteringListRequestParams => ({
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
export const getUserOptionsRequestParams = ({ filters, ...request }: TUsageRequest): TMeteringListRequestParams => ({
    ...getUsageRequestParams({ ...request, filters: _pick(filters, 'project_name') }),
    group_by: [request.period, 'user'],
});

/**
 * The API returns every row of a request, so the sum of the rows is the total.
 */
export const getUsageTotal = (rows: IMeteringRow[]): IMeteringRow => ({
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
const getUsagePeriod = (row: IMeteringRow) => row.day ?? row.month ?? '';

export const compareUsagePeriods = (a: IMeteringRow, b: IMeteringRow) => getUsagePeriod(a).localeCompare(getUsagePeriod(b));

export const formatUsagePeriod = (row: IMeteringRow) => {
    if (row.day) {
        return format(parseISO(row.day), 'MM/dd/yyyy');
    }

    return row.month ? format(parseISO(row.month), 'MM/yyyy') : '';
};
