import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ToggleProps } from '@cloudscape-design/components';

import type { PropertyFilterProps } from 'components';

import { useLocalStorageState } from 'hooks';
import { EMPTY_QUERY, requestParamsToTokens, tokensToRequestParams, tokensToSearchParams } from 'libs/filters';
import { useLazyGetProjectsQuery } from 'services/project';

type RequestParamsKeys = keyof Pick<TInstanceListRequestParams, 'only_active' | 'project_names' | 'fleet_ids'>;

const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAMES: 'project_names',
    FLEET_IDS: 'fleet_ids',
};

const limit = 100;

export const useFilters = () => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [onlyActive, setOnlyActive] = useLocalStorageState('instance-list-filter-only-active', true);
    const [dynamicFilteringOptions, setDynamicFilteringOptions] = useState<PropertyFilterProps.FilteringOption[]>([]);
    const [filteringStatusType, setFilteringStatusType] = useState<PropertyFilterProps.StatusType | undefined>();
    const [getProjects] = useLazyGetProjectsQuery();

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() => {
        return requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys });
    });

    const clearFilter = () => {
        setSearchParams({});
        setPropertyFilterQuery(EMPTY_QUERY);
    };

    const filteringOptions = useMemo(() => {
        return [...dynamicFilteringOptions];
    }, [dynamicFilteringOptions]);

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
            groupValuesLabel: 'Fleet ID values',
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

    const handleLoadItems: PropertyFilterProps['onLoadItems'] = async ({ detail: { filteringProperty, filteringText } }) => {
        setDynamicFilteringOptions([]);

        console.log({ filteringProperty, filteringText });

        if (!filteringText.length) {
            return Promise.resolve();
        }

        setFilteringStatusType('loading');

        if (filteringProperty?.key === filterKeys.PROJECT_NAMES) {
            await getProjects({ name_pattern: filteringText, limit })
                .unwrap()
                .then(({ data }) =>
                    data.map(({ project_name }) => ({
                        propertyKey: filterKeys.PROJECT_NAMES,
                        value: project_name,
                    })),
                )
                .then(setDynamicFilteringOptions);
        }

        setFilteringStatusType(undefined);
    };

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
        filteringStatusType,
        handleLoadItems,
    } as const;
};
