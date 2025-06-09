import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { PropertyFilterProps } from 'components';

import { useProjectFilter } from 'hooks/useProjectFilter';

type Args = {
    localStorePrefix: string;
};

type RequestParamsKeys = keyof Pick<TRunsRequestParams, 'only_active' | 'project_name' | 'username'>;

const FilterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    USER_NAME: 'username',
    ACTIVE: 'only_active',
};

const EMPTY_QUERY: PropertyFilterProps.Query = {
    tokens: [],
    operation: 'and',
};

const tokensToRequestParams = (tokens: PropertyFilterProps.Query['tokens']) => {
    return tokens.reduce((acc, token) => {
        if (token.propertyKey) {
            acc[token.propertyKey as RequestParamsKeys] = token.value;
        }

        return acc;
    }, {} as Record<RequestParamsKeys, string>);
};

export const useFilters = ({ localStorePrefix }: Args) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const { projectOptions } = useProjectFilter({ localStorePrefix });

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

        options.push({
            propertyKey: FilterKeys.ACTIVE,
            value: 'True',
        });

        return options;
    }, [projectOptions]);

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
        {
            key: FilterKeys.ACTIVE,
            operators: ['='],
            propertyLabel: 'Only active',
            groupValuesLabel: 'Active values',
        },
    ];

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        const { tokens, operation } = detail;

        const filteredTokens = tokens.filter((token, tokenIndex) => {
            return !tokens.some((item, index) => token.propertyKey === item.propertyKey && index > tokenIndex);
        });

        setSearchParams(tokensToRequestParams(filteredTokens));

        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const filteringRequestParams = useMemo(() => {
        const params = tokensToRequestParams(propertyFilterQuery.tokens);

        return {
            ...params,
            only_active: params.only_active === 'True',
        };
    }, [propertyFilterQuery]);

    return {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
    } as const;
};
