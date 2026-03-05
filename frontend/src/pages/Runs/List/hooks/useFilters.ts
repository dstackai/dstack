import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ToggleProps } from '@cloudscape-design/components';

import type { PropertyFilterProps } from 'components';

import { useLocalStorageState } from 'hooks';
import { EMPTY_QUERY, requestParamsToTokens, tokensToRequestParams, tokensToSearchParams } from 'libs/filters';
import { useLazyGetProjectsQuery } from 'services/project';
import { useLazyGetUserListQuery } from 'services/user';

type RequestParamsKeys = keyof Pick<TRunsRequestParams, 'only_active' | 'project_name' | 'username'>;

const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    USER_NAME: 'username',
};

const limit = 100;

export const useFilters = () => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [onlyActive, setOnlyActive] = useLocalStorageState('run-list-filter-only-active', true);
    const [filteringOptions, setFilteringOptions] = useState<PropertyFilterProps.FilteringOption[]>([]);
    const [filteringStatusType, setFilteringStatusType] = useState<PropertyFilterProps.StatusType | undefined>();
    const [getProjects] = useLazyGetProjectsQuery();
    const [getUsers] = useLazyGetUserListQuery();

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() =>
        requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys }),
    );

    const clearFilter = () => {
        setSearchParams({});
        setPropertyFilterQuery(EMPTY_QUERY);
    };

    const filteringProperties = useMemo<PropertyFilterProps.FilteringProperty[]>(
        () => [
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
        ],
        [],
    );

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        const { tokens, operation } = detail;

        const filteredTokens = tokens.filter((token, tokenIndex) => {
            return !tokens.some((item, index) => token.propertyKey === item.propertyKey && index > tokenIndex);
        });

        setSearchParams(tokensToSearchParams<RequestParamsKeys>(filteredTokens, onlyActive));

        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const onChangeOnlyActive: ToggleProps['onChange'] = ({ detail }) => {
        setOnlyActive(detail.checked);
    };

    const filteringRequestParams = useMemo(() => {
        const params = tokensToRequestParams<RequestParamsKeys>({
            tokens: propertyFilterQuery.tokens,
        });

        return {
            ...params,
            only_active: onlyActive,
        } as Partial<TRunsRequestParams>;
    }, [propertyFilterQuery, onlyActive]);

    const handleLoadItems: PropertyFilterProps['onLoadItems'] = async ({ detail: { filteringProperty, filteringText } }) => {
        setFilteringOptions([]);

        if (!filteringText.length) {
            return Promise.resolve();
        }

        setFilteringStatusType('loading');

        if (filteringProperty?.key === filterKeys.PROJECT_NAME) {
            await getProjects({ name_pattern: filteringText, limit })
                .unwrap()
                .then(({ data }) =>
                    data.map(({ project_name }) => ({
                        propertyKey: filterKeys.PROJECT_NAME,
                        value: project_name,
                    })),
                )
                .then(setFilteringOptions);
        }

        if (filteringProperty?.key === filterKeys.USER_NAME) {
            await getUsers({ name_pattern: filteringText, limit })
                .unwrap()
                .then(({ data }) =>
                    data.map(({ username }) => ({
                        propertyKey: filterKeys.USER_NAME,
                        value: username,
                    })),
                )
                .then(setFilteringOptions);
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
        filteringStatusType,
        handleLoadItems,
    } as const;
};
