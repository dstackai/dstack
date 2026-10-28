import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { sub } from 'date-fns';

import type { DateRangePickerProps } from 'components';

const searchParamKeys = {
    FROM: 'from',
    TO: 'to',
    LAST: 'last',
};

const timeUnitCodes: Record<DateRangePickerProps.TimeUnit, string> = {
    second: 's',
    minute: 'min',
    hour: 'h',
    day: 'd',
    week: 'w',
    month: 'mo',
    year: 'y',
};

export const relativeOptions: DateRangePickerProps.RelativeOption[] = [
    { key: 'last-15-minutes', amount: 15, unit: 'minute', type: 'relative' },
    { key: 'last-1-hour', amount: 1, unit: 'hour', type: 'relative' },
    { key: 'last-1-day', amount: 1, unit: 'day', type: 'relative' },
    { key: 'last-7-days', amount: 7, unit: 'day', type: 'relative' },
    { key: 'last-30-days', amount: 30, unit: 'day', type: 'relative' },
];

export const useTimeRange = ({ withSearchParams, ascending }: { withSearchParams?: boolean; ascending: boolean }) => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();

    const [timeRange, setTimeRange] = useState<DateRangePickerProps.Value | null>(() =>
        withSearchParams ? searchParamsToTimeRange(searchParams) : null,
    );
    const [now, setNow] = useState<Date>(() => new Date());

    const updateSearchParams = (update: (searchParams: URLSearchParams) => void) => {
        if (!withSearchParams) {
            return;
        }

        setSearchParams((prevSearchParams) => {
            const nextSearchParams = new URLSearchParams(prevSearchParams);
            update(nextSearchParams);
            return nextSearchParams;
        });
    };

    const onChangeTimeRange: DateRangePickerProps['onChange'] = ({ detail }) => {
        setTimeRange(detail.value);
        setNow(new Date());
        updateSearchParams((params) => timeRangeToSearchParams(detail.value, params));
    };

    // Relative time range bounds are calculated from the current time,
    // so updating it reloads the list with the new bounds.
    const refreshRelativeTimeRange = (): boolean => {
        if (timeRange?.type !== 'relative') {
            return false;
        }

        setNow(new Date());
        return true;
    };

    const { start, end } = useMemo(() => getTimeRangeBounds(timeRange, now), [timeRange, now]);

    // The list starts from the time range bound that comes first in the sort order.
    // The other bound is enforced on the client side by isPastEnd.
    const requestParams = useMemo<Pick<TEventListRequestParams, 'ascending' | 'prev_recorded_at'>>(() => {
        // prev_recorded_at is exclusive, so shift the start bound to include events recorded exactly at it
        const firstRecordedAt = ascending ? start && new Date(start.getTime() - 1) : end;

        return {
            ascending,
            ...(firstRecordedAt ? { prev_recorded_at: firstRecordedAt.toISOString() } : {}),
        };
    }, [ascending, start, end]);

    const isPastEnd = useCallback(
        (event: IEvent) => {
            const recordedAt = new Date(event.recorded_at);

            if (ascending) {
                return end !== undefined && recordedAt >= end;
            }

            return start !== undefined && recordedAt < start;
        },
        [ascending, start, end],
    );

    const isValidRange: DateRangePickerProps.ValidationFunction = (range) => {
        if (range?.type === 'absolute') {
            if (!range.startDate || !range.endDate) {
                return { valid: false, errorMessage: t('events.time_range_incomplete') };
            }

            if (new Date(range.startDate) > new Date(range.endDate)) {
                return { valid: false, errorMessage: t('events.time_range_start_after_end') };
            }
        }

        if (range?.type === 'relative' && !(range.amount > 0)) {
            return { valid: false, errorMessage: t('events.time_range_invalid_duration') };
        }

        return { valid: true };
    };

    return {
        timeRange,
        onChangeTimeRange,
        isValidRange,
        refreshRelativeTimeRange,
        requestParams,
        isPastEnd,
    } as const;
};

const getTimeRangeBounds = (timeRange: DateRangePickerProps.Value | null, now: Date): { start?: Date; end?: Date } => {
    if (!timeRange) {
        return {};
    }

    if (timeRange.type === 'relative') {
        return { start: sub(now, { [`${timeRange.unit}s`]: timeRange.amount }) };
    }

    // The picker sets the end time with second precision, e.g. 23:59:59,
    // so include all events recorded within that second.
    return {
        start: new Date(timeRange.startDate),
        end: new Date(new Date(timeRange.endDate).getTime() + 1000),
    };
};

const searchParamsToTimeRange = (searchParams: URLSearchParams): DateRangePickerProps.Value | null => {
    const from = searchParams.get(searchParamKeys.FROM);
    const to = searchParams.get(searchParamKeys.TO);

    if (from && to) {
        return { type: 'absolute', startDate: from, endDate: to };
    }

    const last = searchParams.get(searchParamKeys.LAST);
    const match = last?.match(/^(\d+)([a-z]+)$/);
    const unit = Object.entries(timeUnitCodes).find(([, code]) => code === match?.[2])?.[0];

    if (!match || !unit) {
        return null;
    }

    const value: DateRangePickerProps.RelativeValue = {
        type: 'relative',
        amount: Number(match[1]),
        unit: unit as DateRangePickerProps.TimeUnit,
    };
    const option = relativeOptions.find(({ amount, unit }) => amount === value.amount && unit === value.unit);

    return option ? { ...value, key: option.key } : value;
};

const timeRangeToSearchParams = (timeRange: DateRangePickerProps.Value | null, searchParams: URLSearchParams) => {
    searchParams.delete(searchParamKeys.FROM);
    searchParams.delete(searchParamKeys.TO);
    searchParams.delete(searchParamKeys.LAST);

    if (timeRange?.type === 'absolute') {
        searchParams.set(searchParamKeys.FROM, timeRange.startDate);
        searchParams.set(searchParamKeys.TO, timeRange.endDate);
    }

    if (timeRange?.type === 'relative') {
        searchParams.set(searchParamKeys.LAST, `${timeRange.amount}${timeUnitCodes[timeRange.unit]}`);
    }
};
