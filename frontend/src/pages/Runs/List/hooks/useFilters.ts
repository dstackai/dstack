import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ToggleProps } from '@cloudscape-design/components';

import type { PropertyFilterProps } from 'components';

import { useProjectFilter } from 'hooks/useProjectFilter';

import { useGetUserListQuery } from '../../../../services/user';

type Args = {
    localStorePrefix: string;
};

type RequestParamsKeys = keyof Pick<TRunsRequestParams, 'only_active' | 'project_name' | 'username'>;

const FilterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    USER_NAME: 'username',
};

const EMPTY_QUERY: PropertyFilterProps.Query = {
    tokens: [],
    operation: 'and',
};

const tokensToRequestParams = (tokens: PropertyFilterProps.Query['tokens'], onlyActive?: boolean) => {
    const params = tokens.reduce((acc, token) => {
        if (token.propertyKey) {
            acc[token.propertyKey as RequestParamsKeys] = token.value;
        }

        return acc;
    }, {} as Record<RequestParamsKeys, string>);

    if (onlyActive) {
        params['only_active'] = 'true';
    }

    return params;
};

export const useFilters = ({ localStorePrefix }: Args) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [onlyActive, setOnlyActive] = useState(() => searchParams.get('only_active') === 'true');
    const { projectOptions } = useProjectFilter({ localStorePrefix });
    const { data: usersData } = useGetUserListQuery();

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() => {
        const tokens = [];

        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        for (const [paramKey, paramValue] of searchParams.entries()) {
            if (Object.values(FilterKeys).includes(paramKey)) {
                tokens.push({ propertyKey: paramKey, operator: '=', value: paramValue });
            }
        }

        if (!tokens.length) {
            return EMPTY_QUERY;
        }

        return {
            ...EMPTY_QUERY,
            tokens,
        };
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
                    propertyKey: FilterKeys.PROJECT_NAME,
                    value,
                });
        });

        usersData?.forEach(({ username }) => {
            options.push({
                propertyKey: FilterKeys.USER_NAME,
                value: username,
            });
        });

        return options;
    }, [projectOptions, usersData]);

    const filteringProperties = [
        {
            key: FilterKeys.PROJECT_NAME,
            operators: ['='],
            propertyLabel: 'Project',
            groupValuesLabel: 'Project values',
        },
        {
            key: FilterKeys.USER_NAME,
            operators: ['='],
            propertyLabel: 'User',
        },
    ];

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        const { tokens, operation } = detail;

        const filteredTokens = tokens.filter((token, tokenIndex) => {
            return !tokens.some((item, index) => token.propertyKey === item.propertyKey && index > tokenIndex);
        });

        setSearchParams(tokensToRequestParams(filteredTokens, onlyActive));

        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const onChangeOnlyActive: ToggleProps['onChange'] = ({ detail }) => {
        setOnlyActive(detail.checked);

        setSearchParams(tokensToRequestParams(propertyFilterQuery.tokens, detail.checked));
    };

    const filteringRequestParams = useMemo(() => {
        const params = tokensToRequestParams(propertyFilterQuery.tokens);

        return {
            ...params,
            only_active: onlyActive,
        };
    }, [propertyFilterQuery, onlyActive]);

    return {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        onlyActive,
        onChangeOnlyActive,
    } as const;
};
