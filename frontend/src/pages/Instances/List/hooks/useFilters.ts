import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ToggleProps } from '@cloudscape-design/components';

import type { PropertyFilterProps } from 'components';

import { useProjectFilter } from 'hooks/useProjectFilter';
import { EMPTY_QUERY, requestParamsToTokens, tokensToRequestParams, tokensToSearchParams } from 'libs/filters';

type RequestParamsKeys = keyof Pick<TInstanceListRequestParams, 'only_active' | 'project_names' | 'fleet_ids'>;

const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAMES: 'project_names',
    FLEET_IDS: 'fleet_ids',
};

export const useFilters = (localStorePrefix = 'instances-list-page') => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [onlyActive, setOnlyActive] = useState(() => searchParams.get('only_active') === 'true');
    const { projectOptions } = useProjectFilter({ localStorePrefix });

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() => {
        console.log(requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys }));

        return requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys });
    });

    const clearFilter = () => {
        setSearchParams({});
        setOnlyActive(false);
        setPropertyFilterQuery(EMPTY_QUERY);
    };

    const filteringOptions = useMemo(() => {
        const options: PropertyFilterProps.FilteringOption[] = [];

        projectOptions.forEach(({ value }) => {
            if (value)
                options.push({
                    propertyKey: filterKeys.PROJECT_NAMES,
                    value,
                });
        });

        return options;
    }, [projectOptions]);

    const filteringProperties = [
        {
            key: filterKeys.PROJECT_NAMES,
            operators: ['='],
            propertyLabel: 'Project',
            groupValuesLabel: 'Project values',
        },
        {
            key: filterKeys.FLEET_IDS,
            operators: ['='],
            propertyLabel: 'Fleet ID',
        },
    ];

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        const { tokens, operation } = detail;

        setSearchParams(tokensToSearchParams<RequestParamsKeys>(tokens, onlyActive));

        setPropertyFilterQuery({
            operation,
            tokens,
        });
    };

    const onChangeOnlyActive: ToggleProps['onChange'] = ({ detail }) => {
        setOnlyActive(detail.checked);

        setSearchParams(tokensToSearchParams<RequestParamsKeys>(propertyFilterQuery.tokens, detail.checked));
    };

    const filteringRequestParams = useMemo(() => {
        const params = tokensToRequestParams<RequestParamsKeys>({
            tokens: propertyFilterQuery.tokens,
            arrayFieldKeys: [filterKeys.PROJECT_NAMES, filterKeys.FLEET_IDS],
        });

        return {
            ...params,
            only_active: onlyActive,
        } as Partial<TInstanceListRequestParams>;
    }, [propertyFilterQuery, onlyActive]);

    const isDisabledClearFilter = !propertyFilterQuery.tokens.length && !onlyActive;

    return {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        onlyActive,
        onChangeOnlyActive,
        isDisabledClearFilter,
    } as const;
};
