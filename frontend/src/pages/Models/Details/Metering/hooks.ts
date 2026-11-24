import { useEffect, useMemo, useState } from 'react';

import type { DateRangePickerProps, PropertyFilterProps } from 'components';

import { EMPTY_QUERY, tokensToRequestParams } from 'libs/filters';
import { useLazyGetMeteringQuery } from 'services/metering';

import { useIsValidRange } from 'pages/Events/List/hooks/useTimeRange';

import { DEFAULT_TIME_RANGES, getFilteringOptions, TMeteringFilters, TMeteringPeriod } from './helpers';

type RequestParamsKeys = keyof TMeteringFilters;

const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    USER_NAME: 'user_name',
};

export const useFilters = () => {
    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(EMPTY_QUERY);

    const filteringProperties = [
        {
            key: filterKeys.PROJECT_NAME,
            operators: ['='],
            propertyLabel: 'Project',
            groupValuesLabel: 'Project values',
        },
        {
            key: filterKeys.USER_NAME,
            operators: ['='],
            propertyLabel: 'User',
            groupValuesLabel: 'User values',
        },
    ];

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        const { tokens, operation } = detail;

        const filteredTokens = tokens.filter((token, tokenIndex) => {
            return !tokens.some((item, index) => token.propertyKey === item.propertyKey && index > tokenIndex);
        });

        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const filteringRequestParams = useMemo(() => {
        return tokensToRequestParams<RequestParamsKeys>({
            tokens: propertyFilterQuery.tokens,
        }) as TMeteringFilters;
    }, [propertyFilterQuery]);

    return {
        filteringRequestParams,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringProperties,
    } as const;
};

/**
 * The rows have every project that the filter can narrow them to. The rows that a filter has narrowed
 * lack the others, so the options are those of all the rows since the tab opened.
 */
export const useFilteringOptions = (rows?: IMeteringRow[]) => {
    const [filteringOptions, setFilteringOptions] = useState<PropertyFilterProps.FilteringOption[]>([]);

    useEffect(() => {
        if (rows) {
            setFilteringOptions((options) => getFilteringOptions(rows, options));
        }
    }, [rows]);

    return filteringOptions;
};

/**
 * The rows don't have users, so the users that the filter offers are loaded when its User property opens.
 */
export const useUserFilteringOptions = (requestParams: TMeteringListRequestParams) => {
    const [getMetering] = useLazyGetMeteringQuery();
    const [userFilteringOptions, setUserFilteringOptions] = useState<PropertyFilterProps.FilteringOption[]>([]);
    const [filteringStatusType, setFilteringStatusType] = useState<PropertyFilterProps.StatusType | undefined>();

    const handleLoadItems: PropertyFilterProps['onLoadItems'] = async ({ detail: { filteringProperty } }) => {
        if (filteringProperty?.key !== filterKeys.USER_NAME) {
            return;
        }

        setFilteringStatusType('loading');

        // An answer that the tab already has is used again, so typing a name sends no request
        const { data: rows = [] } = await getMetering(requestParams, true);

        setUserFilteringOptions(getFilteringOptions(rows, []));
        setFilteringStatusType(undefined);
    };

    return {
        userFilteringOptions,
        filteringStatusType,
        handleLoadItems,
    } as const;
};

/**
 * Each period keeps its own time range: a time range in days has no exact form in months.
 */
export const useTimeRange = (period: TMeteringPeriod) => {
    const isValidRange = useIsValidRange();
    const [timeRanges, setTimeRanges] = useState(DEFAULT_TIME_RANGES);

    const onChangeTimeRange: DateRangePickerProps['onChange'] = ({ detail }) => {
        const { value } = detail;

        if (value) {
            setTimeRanges((timeRanges) => ({ ...timeRanges, [period]: value }));
        }
    };

    return {
        timeRange: timeRanges[period],
        onChangeTimeRange,
        isValidRange,
    } as const;
};
