import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { PropertyFilterProps } from 'components';

import { EMPTY_QUERY, requestParamsToTokens, tokensToRequestParams, tokensToSearchParams } from 'libs/filters';

import { useProjectFilter } from '../../../../hooks/useProjectFilter';
import { getPropertyFilterOptions } from '../helpers';

type Args = {
    gpus: IGpu[];
};

type RequestParamsKeys = 'project_name' | 'gpu_name' | 'gpu_count' | 'gpu_memory' | 'backend' | 'spot_policy';

export const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    GPU_NAME: 'gpu_name',
    GPU_COUNT: 'gpu_count',
    GPU_MEMORY: 'gpu_memory',
    BACKEND: 'backend',
    SPOT_POLICY: 'spot_policy',
};

const multipleChoiseKeys: RequestParamsKeys[] = ['gpu_name', 'backend'];

const spotPolicyOptions = [
    {
        propertyKey: filterKeys.SPOT_POLICY,
        value: 'spot',
    },
    {
        propertyKey: filterKeys.SPOT_POLICY,
        value: 'on-demand',
    },
    {
        propertyKey: filterKeys.SPOT_POLICY,
        value: 'auto',
    },
];

export const useFilters = ({ gpus }: Args) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const { projectOptions } = useProjectFilter({ localStorePrefix: 'offers-list-projects' });
    const projectNameIsChecked = useRef(false);

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() =>
        requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys }),
    );

    const clearFilter = () => {
        setSearchParams({});
        setPropertyFilterQuery(EMPTY_QUERY);
    };

    const filteringOptions = useMemo(() => {
        const options: PropertyFilterProps.FilteringOption[] = [...spotPolicyOptions];

        const { names, backends } = getPropertyFilterOptions(gpus);

        projectOptions.forEach(({ value }) => {
            if (value)
                options.push({
                    propertyKey: filterKeys.PROJECT_NAME,
                    value,
                });
        });

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

        return options;
    }, [gpus]);

    const filteringProperties = [
        {
            key: filterKeys.PROJECT_NAME,
            operators: ['='],
            propertyLabel: 'Project',
        },
        {
            key: filterKeys.GPU_NAME,
            operators: ['='],
            propertyLabel: 'GPU names',
        },
        {
            key: filterKeys.GPU_COUNT,
            operators: ['<=', '>='],
            propertyLabel: 'GPU count',
        },
        {
            key: filterKeys.GPU_MEMORY,
            operators: ['<=', '>='],
            propertyLabel: 'GPU Memory',
        },
        {
            key: filterKeys.BACKEND,
            operators: ['='],
            propertyLabel: 'Backends',
        },
        {
            key: filterKeys.SPOT_POLICY,
            operators: ['='],
            propertyLabel: 'Spot',
        },
    ];

    const onChangePropertyFilterHandle = ({ tokens, operation }: PropertyFilterProps.Query) => {
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

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        onChangePropertyFilterHandle(detail);
    };

    const filteringRequestParams = useMemo(() => {
        console.log({ tokens: propertyFilterQuery.tokens });

        const params = tokensToRequestParams<RequestParamsKeys>({
            tokens: propertyFilterQuery.tokens,
            arrayFieldKeys: multipleChoiseKeys,
        });

        return {
            ...params,
        } as Partial<TRunsRequestParams>;
    }, [propertyFilterQuery]);

    useEffect(() => {
        if (!projectNameIsChecked.current && projectOptions.length) {
            projectNameIsChecked.current = true;

            if (!filteringRequestParams['project_name']) {
                onChangePropertyFilterHandle({
                    tokens: [
                        ...propertyFilterQuery.tokens,
                        {
                            operator: '=',
                            propertyKey: filterKeys.PROJECT_NAME,
                            value: projectOptions[0].value,
                        },
                    ],
                    operation: 'and',
                });
            }
        }
    }, [projectOptions]);

    return {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
    } as const;
};
