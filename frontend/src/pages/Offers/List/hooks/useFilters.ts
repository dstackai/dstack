import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { MultiselectProps, PropertyFilterProps } from 'components';

import {
    EMPTY_QUERY,
    requestParamsToArray,
    requestParamsToTokens,
    tokensToRequestParams,
    tokensToSearchParams,
} from 'libs/filters';
import { useGetProjectsQuery, useLazyGetProjectsQuery } from 'services/project';

import { getPropertyFilterOptions } from '../helpers';

type RequestParamsKeys = 'project_name' | 'gpu_name' | 'gpu_count' | 'gpu_memory' | 'backend' | 'spot_policy' | 'group_by';

export type UseFiltersArgs = {
    gpus: IGpu[];
    withSearchParams?: boolean;
    permanentFilters?: Partial<Record<RequestParamsKeys, string>>;
    defaultFilters?: Partial<Record<RequestParamsKeys, string>>;
};

export const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    GPU_NAME: 'gpu_name',
    GPU_COUNT: 'gpu_count',
    GPU_MEMORY: 'gpu_memory',
    BACKEND: 'backend',
    SPOT_POLICY: 'spot_policy',
};

const multipleChoiceKeys: RequestParamsKeys[] = ['gpu_name', 'backend'];

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

const filteringProperties = [
    {
        key: filterKeys.PROJECT_NAME,
        operators: ['='],
        propertyLabel: 'Project',
        groupValuesLabel: 'Project values',
    },
    {
        key: filterKeys.GPU_NAME,
        operators: ['='],
        propertyLabel: 'GPU name',
        groupValuesLabel: 'GPU name values',
    },
    {
        key: filterKeys.GPU_COUNT,
        operators: ['<=', '>='],
        propertyLabel: 'GPU count',
        groupValuesLabel: 'GPU count values',
    },
    {
        key: filterKeys.GPU_MEMORY,
        operators: ['<=', '>='],
        propertyLabel: 'GPU memory',
        groupValuesLabel: 'GPU memory values',
    },
    {
        key: filterKeys.BACKEND,
        operators: ['='],
        propertyLabel: 'Backend',
        groupValuesLabel: 'Backend values',
    },
    {
        key: filterKeys.SPOT_POLICY,
        operators: ['='],
        propertyLabel: 'Spot policy',
        groupValuesLabel: 'Spot policy values',
    },
];

const gpuFilterOption = { label: 'GPU', value: 'gpu' };
const defaultGroupByOptions = [{ ...gpuFilterOption }, { label: 'Backend', value: 'backend' }];
const groupByRequestParamName: RequestParamsKeys = 'group_by';
const limit = 100;

export const useFilters = ({ gpus, withSearchParams = true, permanentFilters = {}, defaultFilters }: UseFiltersArgs) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [dynamicFilteringOptions, setDynamicFilteringOptions] = useState<PropertyFilterProps.FilteringOption[]>([]);
    const [filteringStatusType, setFilteringStatusType] = useState<PropertyFilterProps.StatusType | undefined>();
    const [getProjects] = useLazyGetProjectsQuery();
    const { data: projectsData } = useGetProjectsQuery({ limit: 1 });
    const projectNameIsChecked = useRef(false);

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() =>
        requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys, defaultFilterValues: defaultFilters }),
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
        const options: PropertyFilterProps.FilteringOption[] = [...spotPolicyOptions, ...dynamicFilteringOptions];

        const { names, backends } = getPropertyFilterOptions(gpus);

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
    }, [gpus, dynamicFilteringOptions]);

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

    const filteringPropertiesForShowing = useMemo(() => {
        const permanentFilterKeys = Object.keys(permanentFilters);
        return filteringProperties.filter(({ key }) => !permanentFilterKeys.includes(key));
    }, [permanentFilters]);

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

    const onChangePropertyFilterHandle = ({ tokens, operation }: PropertyFilterProps.Query) => {
        const filteredTokens = tokens.filter((token, tokenIndex) => {
            return (
                multipleChoiceKeys.includes(token.propertyKey as RequestParamsKeys) ||
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
            arrayFieldKeys: multipleChoiceKeys,
        });

        return {
            ...params,
            ...permanentFilters,
        };
    }, [propertyFilterQuery, permanentFilters]);

    const handleLoadItems: PropertyFilterProps['onLoadItems'] = async ({ detail: { filteringProperty, filteringText } }) => {
        setDynamicFilteringOptions([]);

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
                .then(setDynamicFilteringOptions);
        }

        setFilteringStatusType(undefined);
    };

    useEffect(() => {
        if (!projectNameIsChecked.current && projectsData?.data?.length) {
            projectNameIsChecked.current = true;

            if (!filteringRequestParams['project_name']) {
                onChangePropertyFilterHandle({
                    tokens: [
                        ...propertyFilterQuery.tokens,
                        {
                            operator: '=',
                            propertyKey: filterKeys.PROJECT_NAME,
                            value: projectsData.data[0].project_name,
                        },
                    ],
                    operation: 'and',
                });
            }
        }
    }, [projectsData]);

    return {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties: filteringPropertiesForShowing,
        groupBy,
        groupByOptions,
        onChangeGroupBy,
        filteringStatusType,
        handleLoadItems,
    } as const;
};
