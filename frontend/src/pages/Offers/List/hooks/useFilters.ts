import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { PropertyFilterProps } from 'components';

import { EMPTY_QUERY, requestParamsToTokens, tokensToRequestParams, tokensToSearchParams } from 'libs/filters';

import { getPropertyFilterOptions } from '../helpers';

type Args = {
    gpus: IGpu[];
};

type RequestParamsKeys = 'gpu_name' | 'gpu_count' | 'gpu_memory' | 'backend';

export const filterKeys: Record<string, RequestParamsKeys> = {
    GPU_NAME: 'gpu_name',
    GPU_COUNT: 'gpu_count',
    GPU_MEMORY: 'gpu_memory',
    BACKEND: 'backend',
};

const multipleChoiseKeys: RequestParamsKeys[] = ['gpu_name', 'backend'];

export const useFilters = ({ gpus }: Args) => {
    const [searchParams, setSearchParams] = useSearchParams();

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() =>
        requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys }),
    );

    const clearFilter = () => {
        setSearchParams({});
        setPropertyFilterQuery(EMPTY_QUERY);
    };

    const filteringOptions = useMemo(() => {
        const options: PropertyFilterProps.FilteringOption[] = [];

        const { names, backends, counts } = getPropertyFilterOptions(gpus);

        Array.from(names).forEach((name) => {
            options.push({
                propertyKey: filterKeys.GPU_NAME,
                value: name,
            });
        });

        Array.from(backends).forEach((backend) => {
            options.push({
                propertyKey: filterKeys.BACKEND,
                value: backend,
            });
        });

        Array.from(counts).forEach((count) => {
            options.push({
                propertyKey: filterKeys.GPU_COUNT,
                value: count,
            });
        });

        return options;
    }, [gpus]);

    const filteringProperties = [
        {
            key: filterKeys.GPU_NAME,
            operators: ['='],
            propertyLabel: 'GPU Name',
        },
        {
            key: filterKeys.GPU_COUNT,
            operators: ['='],
            propertyLabel: 'GPU Count',
        },
        // {
        //     key: filterKeys.GPU_MEMORY,
        //     operators: ['='],
        //     propertyLabel: 'GPU Memory',
        // },
        {
            key: filterKeys.BACKEND,
            operators: ['='],
            propertyLabel: 'Backend',
        },
    ];

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        const { tokens, operation } = detail;

        const filteredTokens = tokens.filter((token, tokenIndex) => {
            return (
                multipleChoiseKeys.includes(token.propertyKey as RequestParamsKeys) ||
                !tokens.some((item, index) => token.propertyKey === item.propertyKey && index > tokenIndex)
            );
        });

        setSearchParams(tokensToSearchParams<RequestParamsKeys>(filteredTokens));

        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const filteringRequestParams = useMemo(() => {
        const params = tokensToRequestParams<RequestParamsKeys>({
            tokens: propertyFilterQuery.tokens,
            arrayFieldKeys: multipleChoiseKeys,
        });

        return {
            ...params,
        } as Partial<TRunsRequestParams>;
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
