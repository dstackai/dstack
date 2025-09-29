import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { MultiselectProps, PropertyFilterProps } from 'components';

import { useProjectFilter } from 'hooks/useProjectFilter';
import {
    EMPTY_QUERY,
    requestParamsToArray,
    requestParamsToTokens,
    tokensToRequestParams,
    tokensToSearchParams,
} from 'libs/filters';

import { getPropertyFilterOptions } from '../helpers';

type Args = {
    gpus: IGpu[];
    withSearchParams?: boolean;
};

type RequestParamsKeys = 'project_name' | 'gpu_name' | 'gpu_count' | 'gpu_memory' | 'backend' | 'spot_policy' | 'group_by';

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

const gpuFilterOption = { label: 'GPU', value: 'gpu' };

const defaultGroupByOptions = [{ ...gpuFilterOption }, { label: 'Backend', value: 'backend' }];

const groupByRequestParamName: RequestParamsKeys = 'group_by';

export const useFilters = ({ gpus, withSearchParams = true }: Args) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const { projectOptions } = useProjectFilter({ localStorePrefix: 'offers-list-projects' });
    const projectNameIsChecked = useRef(false);

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() =>
        requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys }),
    );

    const [groupBy, setGroupBy] = useState<MultiselectProps.Options>(() => {
        const selectedGroupBy = requestParamsToArray<RequestParamsKeys>({
            searchParams,
            paramName: groupByRequestParamName,
        });

        if (selectedGroupBy.length) {
            return defaultGroupByOptions.filter(({ value }) => selectedGroupBy.includes(value));
        }

        return [gpuFilterOption];
    });

    const clearFilter = () => {
        if (withSearchParams) {
            setSearchParams({});
        }
        setPropertyFilterQuery(EMPTY_QUERY);
        setGroupBy([]);
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

    const groupByOptions: MultiselectProps.Options = useMemo(() => {
        return defaultGroupByOptions.map((option) => {
            if (option.value === 'gpu' && groupBy.some(({ value }) => value === 'backend')) {
                return {
                    ...option,
                    disabled: true,
                };
            }

            if (option.value === 'backend' && !groupBy.some(({ value }) => value === 'gpu')) {
                return {
                    ...option,
                    disabled: true,
                };
            }

            return option;
        });
    }, [groupBy]);

    const setSearchParamsHandle = ({
        tokens,
        groupBy,
    }: {
        tokens: PropertyFilterProps.Query['tokens'];
        groupBy: MultiselectProps.Options;
    }) => {
        if (!withSearchParams) {
            return;
        }

        const searchParams = tokensToSearchParams<RequestParamsKeys>(tokens);

        groupBy.forEach(({ value }) => searchParams.append(groupByRequestParamName, value as string));

        setSearchParams(searchParams);
    };

    const filteringProperties = [
        {
            key: filterKeys.PROJECT_NAME,
            operators: ['='],
            propertyLabel: 'Project',
        },
        {
            key: filterKeys.GPU_NAME,
            operators: ['='],
            propertyLabel: 'GPU name',
        },
        {
            key: filterKeys.GPU_COUNT,
            operators: ['<=', '>='],
            propertyLabel: 'GPU count',
        },
        {
            key: filterKeys.GPU_MEMORY,
            operators: ['<=', '>='],
            propertyLabel: 'GPU memory',
        },
        {
            key: filterKeys.BACKEND,
            operators: ['='],
            propertyLabel: 'Backend',
        },
        {
            key: filterKeys.SPOT_POLICY,
            operators: ['='],
            propertyLabel: 'Spot policy',
        },
    ];

    const onChangePropertyFilterHandle = ({ tokens, operation }: PropertyFilterProps.Query) => {
        const filteredTokens = tokens.filter((token, tokenIndex) => {
            return (
                multipleChoiseKeys.includes(token.propertyKey as RequestParamsKeys) ||
                !tokens.some((item, index) => token.propertyKey === item.propertyKey && index > tokenIndex)
            );
        });

        setSearchParamsHandle({
            tokens: filteredTokens,
            groupBy: [...groupBy],
        });

        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        onChangePropertyFilterHandle(detail);
    };

    const onChangeGroupBy: MultiselectProps['onChange'] = ({ detail }) => {
        const selectedGpu = detail.selectedOptions.some(({ value }) => value === 'gpu');

        let tempSelectedOptions: MultiselectProps.Options = detail.selectedOptions;

        if (!selectedGpu) {
            tempSelectedOptions = detail.selectedOptions.filter(({ value }) => value !== 'backend');
        }

        setSearchParamsHandle({
            tokens: propertyFilterQuery.tokens,
            groupBy: tempSelectedOptions,
        });

        setGroupBy(tempSelectedOptions);
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
        groupBy,
        groupByOptions,
        onChangeGroupBy,
    } as const;
};
