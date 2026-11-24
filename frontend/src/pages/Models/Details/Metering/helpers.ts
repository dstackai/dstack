import { pick as _pick, sumBy as _sumBy, uniq as _uniq } from 'lodash';
import { add, format, parseISO, sub } from 'date-fns';

import type { DateRangePickerProps, PropertyFilterProps } from 'components';

import { IModelExtended } from '../../List/types';

export type TMeteringPeriod = Extract<TMeteringGroupBy, 'day' | 'month'>;

export type TMeteringFilters = Pick<TMeteringListRequestParams, 'project_name' | 'user_name'>;

const DATE_FORMAT = 'yyyy-MM-dd';

export const DEFAULT_PERIOD: TMeteringPeriod = 'day';

export const DEFAULT_TIME_RANGE: DateRangePickerProps.RelativeOption = {
    key: 'last-30-days',
    amount: 30,
    unit: 'day',
    type: 'relative',
};

export const relativeOptions: DateRangePickerProps.RelativeOption[] = [
    { key: 'last-7-days', amount: 7, unit: 'day', type: 'relative' },
    DEFAULT_TIME_RANGE,
    { key: 'last-3-months', amount: 3, unit: 'month', type: 'relative' },
];

/**
 * Metering sums tokens by UTC day, so a time range covers whole days:
 * from the start of its first day to the end of its last one. A relative time range ends today.
 * By month, the rows sum the same days, so the first and the last month of a time range can be partial.
 */
const getTimeRangeBounds = (
    timeRange: DateRangePickerProps.Value,
    now: Date,
): Pick<TMeteringListRequestParams, 'start' | 'end'> => {
    const today = parseISO(now.toISOString().split('T')[0]);

    const [firstDay, lastDay] =
        timeRange.type === 'relative'
            ? [sub(today, { [`${timeRange.unit}s`]: timeRange.amount }), today]
            : [parseISO(timeRange.startDate), parseISO(timeRange.endDate)];

    return {
        start: `${format(firstDay, DATE_FORMAT)}T00:00:00Z`,
        end: `${format(add(lastDay, { days: 1 }), DATE_FORMAT)}T00:00:00Z`,
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
    ...getTimeRangeBounds(timeRange, now),
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
