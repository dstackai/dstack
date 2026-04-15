import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { MultiselectProps, PropertyFilterProps } from 'components';

import {
    EMPTY_QUERY,
    getNamePatternFilterRequestParams,
    requestParamsToArray,
    requestParamsToTokens,
    tokensToRequestParams,
    tokensToSearchParams,
} from 'libs/filters';
import { useLazyGetProjectFleetsQuery } from 'services/fleet';
import { useGetProjectsQuery, useLazyGetProjectsQuery } from 'services/project';

import { getFleetFilterValue, getPropertyFilterOptions } from '../helpers';

type RequestParamsKeys =
    | 'project_name'
    | 'gpu_name'
    | 'gpu_count'
    | 'gpu_memory'
    | 'backend'
    | 'fleet'
    | 'spot_policy'
    | 'group_by';

export type UseFiltersArgs = {
    gpus: IGpu[];
    withSearchParams?: boolean;
    showFleetFilter?: boolean;
    permanentFilters?: Partial<Record<RequestParamsKeys, string>>;
    defaultFilters?: Partial<Record<RequestParamsKeys, string | string[]>>;
};

export const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    GPU_NAME: 'gpu_name',
    GPU_COUNT: 'gpu_count',
    GPU_MEMORY: 'gpu_memory',
    BACKEND: 'backend',
    FLEET: 'fleet',
    SPOT_POLICY: 'spot_policy',
};

const multipleChoiceKeys: RequestParamsKeys[] = ['gpu_name', 'backend', 'fleet'];

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
        key: filterKeys.FLEET,
        operators: ['='],
        propertyLabel: 'Fleet',
        groupValuesLabel: 'Fleet values',
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

export const useFilters = ({
    gpus,
    withSearchParams = true,
    showFleetFilter = false,
    permanentFilters = {},
    defaultFilters,
}: UseFiltersArgs) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [dynamicFilteringOptions, setDynamicFilteringOptions] = useState<PropertyFilterProps.FilteringOption[]>([]);
    const [filteringStatusType, setFilteringStatusType] = useState<PropertyFilterProps.StatusType | undefined>();
    const [getProjects] = useLazyGetProjectsQuery();
    const [getProjectFleets] = useLazyGetProjectFleetsQuery();
    const { data: projectsData } = useGetProjectsQuery({ limit: 1 });
    const projectNameIsChecked = useRef(false);
    const prevSelectedProjectName = useRef<string | undefined>();

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() => {
        const queryFromSearchParams = requestParamsToTokens<RequestParamsKeys>({
            searchParams,
            filterKeys,
            defaultFilterValues: defaultFilters,
        });

        const tokens = showFleetFilter
            ? queryFromSearchParams.tokens
            : queryFromSearchParams.tokens.filter((token) => token.propertyKey !== filterKeys.FLEET);

        const query = {
            ...queryFromSearchParams,
            tokens,
        };

        if (query.tokens.length > 0) {
            return query;
        }

        return EMPTY_QUERY;
    });

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
        return filteringProperties.filter(({ key }) => {
            if (key === filterKeys.FLEET && !showFleetFilter) {
                return false;
            }

            return !permanentFilterKeys.includes(key);
        });
    }, [permanentFilters, showFleetFilter]);

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

    const selectedProjectName = useMemo(() => {
        const projectName = filteringRequestParams['project_name'];

        return typeof projectName === 'string' ? projectName : undefined;
    }, [filteringRequestParams]);

    const handleLoadItems: PropertyFilterProps['onLoadItems'] = async ({ detail: { filteringProperty, filteringText } }) => {
        setDynamicFilteringOptions([]);

        setFilteringStatusType('loading');

        if (filteringProperty?.key === filterKeys.PROJECT_NAME) {
            await getProjects(getNamePatternFilterRequestParams(filteringText, limit))
                .unwrap()
                .then(({ data }) =>
                    data.map(({ project_name }) => ({
                        propertyKey: filterKeys.PROJECT_NAME,
                        value: project_name,
                    })),
                )
                .then(setDynamicFilteringOptions);
        }

        if (showFleetFilter && filteringProperty?.key === filterKeys.FLEET && selectedProjectName) {
            await getProjectFleets({
                projectName: selectedProjectName,
                includeImported: true,
            })
                .unwrap()
                .then((fleets) =>
                    fleets
                        .map((fleet) => ({
                            propertyKey: filterKeys.FLEET,
                            value: getFleetFilterValue(fleet, selectedProjectName),
                        }))
                        .filter(({ value }) => value.toLowerCase().includes(filteringText.toLowerCase()))
                        .slice(0, limit),
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

    useEffect(() => {
        const prevProjectName = prevSelectedProjectName.current;
        prevSelectedProjectName.current = selectedProjectName;

        if (!showFleetFilter || prevProjectName === selectedProjectName) {
            return;
        }

        if (!propertyFilterQuery.tokens.some((token) => token.propertyKey === filterKeys.FLEET)) {
            return;
        }

        onChangePropertyFilterHandle({
            tokens: propertyFilterQuery.tokens.filter((token) => token.propertyKey !== filterKeys.FLEET),
            operation: propertyFilterQuery.operation,
        });
    }, [propertyFilterQuery, selectedProjectName, showFleetFilter]);

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
