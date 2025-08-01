import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ToggleProps } from '@cloudscape-design/components';

import type { PropertyFilterProps } from 'components';

import { useProjectFilter } from 'hooks/useProjectFilter';
import { EMPTY_QUERY, requestParamsToTokens, tokensToRequestParams, tokensToSearchParams } from 'libs/filters';
import { useGetUserListQuery } from 'services/user';

type Args = {
    localStorePrefix: string;
};

type RequestParamsKeys = keyof Pick<TRunsRequestParams, 'only_active' | 'project_name' | 'username'>;

const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    USER_NAME: 'username',
};

export const useFilters = ({ localStorePrefix }: Args) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [onlyActive, setOnlyActive] = useState(() => searchParams.get('only_active') === 'true');
    const { projectOptions } = useProjectFilter({ localStorePrefix });
    const { data: usersData } = useGetUserListQuery();

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() =>
        requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys }),
    );

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
                    propertyKey: filterKeys.PROJECT_NAME,
                    value,
                });
        });

        usersData?.forEach(({ username }) => {
            options.push({
                propertyKey: filterKeys.USER_NAME,
                value: username,
            });
        });

        return options;
    }, [projectOptions, usersData]);

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
        },
    ];

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

        setSearchParams(tokensToSearchParams<RequestParamsKeys>(propertyFilterQuery.tokens, detail.checked));
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
