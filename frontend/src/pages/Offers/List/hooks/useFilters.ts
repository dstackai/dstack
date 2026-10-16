import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { MultiselectProps, PropertyFilterProps } from 'components';

import { useLocalStorageState } from 'hooks/useLocalStorageState';
import {
    EMPTY_QUERY,
    getTokenAwareNamePatternFilterRequestParams,
    requestParamsToArray,
    requestParamsToTokens,
    tokensToRequestParams,
    tokensToSearchParams,
} from 'libs/filters';
import { useLazyGetProjectFleetsQuery } from 'services/fleet';
import { useGetProjectsQuery, useLazyGetProjectQuery, useLazyGetProjectsQuery } from 'services/project';

import { formatGpuVendor, getFleetFilterValue, getPropertyFilterOptions, rangeToObject } from '../helpers';

type RequestParamsKeys =
    | 'project_name'
    | 'gpu_vendor'
    | 'gpu_name'
    | 'gpu_count'
    | 'gpu_memory'
    | 'cpu_count'
    | 'cpu_arch'
    | 'memory'
    | 'backend'
    | 'region'
    | 'fleet'
    | 'spot_policy'
    | 'group_by';

export type UseFiltersArgs = {
    gpus: (IGpu | ICpuGroup)[];
    withSearchParams?: boolean;
    showFleetFilter?: boolean;
    allowUngrouped?: boolean;
    permanentFilters?: Partial<Record<RequestParamsKeys, string>>;
    defaultFilters?: Partial<Record<RequestParamsKeys, string | string[]>>;
    onChange?: (filters: NonNullable<UseFiltersArgs['defaultFilters']>) => void;
    /** Loads offers for GPU name, vendor and backend suggestions, for a page that doesn't list offers itself. */
    loadGpus?: (projectName: string) => Promise<void>;
};

export const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    GPU_VENDOR: 'gpu_vendor',
    GPU_NAME: 'gpu_name',
    GPU_COUNT: 'gpu_count',
    GPU_MEMORY: 'gpu_memory',
    CPU_COUNT: 'cpu_count',
    CPU_ARCH: 'cpu_arch',
    MEMORY: 'memory',
    BACKEND: 'backend',
    REGION: 'region',
    FLEET: 'fleet',
    SPOT_POLICY: 'spot_policy',
};

const multipleChoiceKeys: RequestParamsKeys[] = ['gpu_name', 'backend', 'fleet'];

/** The offer filters in a URL, as `defaultFilters` takes them. */
export const getOfferFilters = (searchParams: URLSearchParams): UseFiltersArgs['defaultFilters'] => {
    const filters: UseFiltersArgs['defaultFilters'] = {};

    Object.values(filterKeys).forEach((key) => {
        const values = searchParams.getAll(key);

        if (values.length) {
            filters[key] = multipleChoiceKeys.includes(key) ? values : values[0];
        }
    });

    return filters;
};

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

const projectFilteringProperty = {
    key: filterKeys.PROJECT_NAME,
    operators: ['='],
    propertyLabel: 'Project',
    groupValuesLabel: 'Project values',
};

const filteringProperties = [
    projectFilteringProperty,
    {
        key: filterKeys.GPU_VENDOR,
        operators: [{ operator: '=', format: formatGpuVendor }],
        propertyLabel: 'GPU vendor',
        groupValuesLabel: 'GPU vendor values',
    },
    {
        key: filterKeys.GPU_NAME,
        operators: ['='],
        propertyLabel: 'GPU name',
        groupValuesLabel: 'GPU name values',
    },
    {
        key: filterKeys.GPU_COUNT,
        operators: ['=', '<=', '>='],
        propertyLabel: 'GPU count',
        groupValuesLabel: 'GPU count values',
    },
    {
        key: filterKeys.GPU_MEMORY,
        operators: ['=', '<=', '>='],
        propertyLabel: 'GPU memory',
        groupValuesLabel: 'GPU memory values',
    },
    {
        key: filterKeys.CPU_COUNT,
        operators: ['=', '<=', '>='],
        propertyLabel: 'CPU count',
        groupValuesLabel: 'CPU count values',
    },
    {
        key: filterKeys.CPU_ARCH,
        operators: ['='],
        propertyLabel: 'CPU architecture',
        groupValuesLabel: 'CPU architecture values',
    },
    {
        key: filterKeys.MEMORY,
        operators: ['=', '<=', '>='],
        propertyLabel: 'RAM',
        groupValuesLabel: 'RAM values',
    },
    {
        key: filterKeys.BACKEND,
        operators: ['='],
        propertyLabel: 'Backend',
        groupValuesLabel: 'Backend values',
    },
    {
        key: filterKeys.REGION,
        operators: ['='],
        propertyLabel: 'Region',
        groupValuesLabel: 'Region values',
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
const cpuFilterOption = { label: 'CPU', value: 'cpu' };
const defaultGroupByOptions = [gpuFilterOption, cpuFilterOption, { label: 'Backend', value: 'backend' }];
const isResourceGroup = (value?: string) => value === 'gpu' || value === 'cpu';
const getGroupBy = (options: MultiselectProps.Options, gpuEnabled: boolean): MultiselectProps.Options =>
    options.map((option) => (isResourceGroup(option.value) ? (gpuEnabled ? gpuFilterOption : cpuFilterOption) : option));
const groupByRequestParamName: RequestParamsKeys = 'group_by';
const limit = 100;

// Use dstack ranges so bounds and memory units survive URLs and wizard navigation.
export const toRangeTokens = (tokens: PropertyFilterProps.Query['tokens']) =>
    tokens.map((token) => {
        if (!['gpu_count', 'gpu_memory', 'cpu_count', 'memory'].includes(token.propertyKey ?? '')) return token;
        if (token.operator === '>=') return { ...token, operator: '=', value: `${token.value}..` };
        if (token.operator === '<=') return { ...token, operator: '=', value: `..${token.value}` };
        return token;
    });

export const useFilters = ({
    gpus,
    withSearchParams = true,
    showFleetFilter = false,
    allowUngrouped = false,
    permanentFilters = {},
    defaultFilters,
    onChange,
    loadGpus,
}: UseFiltersArgs) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [rememberedProject, setRememberedProject] = useLocalStorageState<string | null>('project-filter-project_name', null);
    const [dynamicFilteringOptions, setDynamicFilteringOptions] = useState<PropertyFilterProps.FilteringOption[]>([]);
    const [filteringStatusType, setFilteringStatusType] = useState<PropertyFilterProps.StatusType | undefined>();
    const [getProjects] = useLazyGetProjectsQuery();
    const [getProject] = useLazyGetProjectQuery();
    const [getProjectFleets] = useLazyGetProjectFleetsQuery();
    const { data: projectsData } = useGetProjectsQuery({ limit: 2 });
    const propertyFilterRef = useRef<PropertyFilterProps.Ref>(null);
    const projectNameIsChecked = useRef(false);
    const prevSelectedProjectName = useRef<string | undefined>();

    // Without search params, the page URL belongs to another page, e.g. the Launch wizard.
    const initialSearchParams = withSearchParams ? searchParams : new URLSearchParams();
    const canAutoSelectCpu = useRef(
        allowUngrouped &&
            withSearchParams &&
            !Array.from(initialSearchParams.keys()).some((key) => key.startsWith('gpu_')) &&
            !Object.keys(defaultFilters ?? {}).some((key) => key.startsWith('gpu_')),
    );

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() => {
        const queryFromSearchParams = requestParamsToTokens<RequestParamsKeys>({
            searchParams: initialSearchParams,
            filterKeys,
            defaultFilterValues:
                defaultFilters &&
                Object.fromEntries(Object.entries(defaultFilters).filter(([key]) => key !== groupByRequestParamName)),
        });

        const tokens = queryFromSearchParams.tokens.filter(
            (token) =>
                !Object.keys(permanentFilters).includes(token.propertyKey ?? '') &&
                (showFleetFilter || token.propertyKey !== filterKeys.FLEET),
        );

        if (
            allowUngrouped &&
            (initialSearchParams.getAll(groupByRequestParamName).includes('cpu') ||
                defaultFilters?.group_by?.includes('cpu')) &&
            !tokens.some(({ propertyKey }) => propertyKey === filterKeys.GPU_COUNT)
        ) {
            tokens.push({ propertyKey: filterKeys.GPU_COUNT, operator: '=', value: '0' });
        }

        const query = {
            ...queryFromSearchParams,
            tokens,
        };

        if (query.tokens.length > 0) {
            return query;
        }

        return EMPTY_QUERY;
    });

    const isCpuModeToken = (token: PropertyFilterProps.Token) =>
        allowUngrouped &&
        token.propertyKey === filterKeys.GPU_COUNT &&
        rangeToObject(toRangeTokens([token])[0].value)?.max === 0;
    const gpuEnabled = !propertyFilterQuery.tokens.some(isCpuModeToken);

    const [groupBy, setGroupBy] = useState<MultiselectProps.Options>(() => {
        if (!withSearchParams && defaultFilters?.group_by !== undefined) {
            return getGroupBy(
                defaultGroupByOptions.filter(({ value }) => defaultFilters.group_by?.includes(value)),
                gpuEnabled,
            );
        }

        const selectedGroupBy = requestParamsToArray<RequestParamsKeys>({
            searchParams: initialSearchParams,
            paramName: groupByRequestParamName,
        });

        if (selectedGroupBy.length || (allowUngrouped && initialSearchParams.has(groupByRequestParamName))) {
            return getGroupBy(
                defaultGroupByOptions.filter(({ value }) => selectedGroupBy.includes(value)),
                gpuEnabled,
            );
        }

        return [gpuEnabled ? gpuFilterOption : cpuFilterOption];
    });

    const hasCustomFilters = propertyFilterQuery.tokens.some(
        (token) => token.propertyKey !== filterKeys.PROJECT_NAME && !isCpuModeToken(token),
    );

    // Keeps the project and the group by, so that clearing leads back to the project's offers.
    const clearFilter = () => {
        onChangePropertyFilterHandle({
            tokens: propertyFilterQuery.tokens.filter(
                (token) => token.propertyKey === filterKeys.PROJECT_NAME || isCpuModeToken(token),
            ),
            operation: propertyFilterQuery.operation,
        });
    };

    const filteringOptions = useMemo(() => {
        const options: PropertyFilterProps.FilteringOption[] = [
            ...['x86', 'arm'].map((value) => ({ propertyKey: filterKeys.CPU_ARCH, value })),
            ...spotPolicyOptions,
            ...dynamicFilteringOptions,
        ];

        const { names, vendors, backends } = getPropertyFilterOptions(gpus);

        Array.from(vendors).forEach((vendor) => {
            options.push({
                propertyKey: filterKeys.GPU_VENDOR,
                value: vendor,
                label: formatGpuVendor(vendor),
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
    }, [gpus, dynamicFilteringOptions]);

    const groupByOptions: MultiselectProps.Options = useMemo(() => {
        return defaultGroupByOptions
            .filter(({ value }) => !isResourceGroup(value) || value === (gpuEnabled ? 'gpu' : 'cpu'))
            .map((option) => {
                if (isResourceGroup(option.value) && groupBy.some(({ value }) => value === 'backend')) {
                    return {
                        ...option,
                        disabled: true,
                    };
                }

                if (option.value === 'backend' && !groupBy.some(({ value }) => isResourceGroup(value))) {
                    return {
                        ...option,
                        disabled: true,
                    };
                }

                return option;
            });
    }, [groupBy, gpuEnabled]);

    const filteringPropertiesForShowing = useMemo(() => {
        const permanentFilterKeys = Object.keys(permanentFilters);
        return filteringProperties.filter(({ key }) => {
            if (!gpuEnabled && key.startsWith('gpu_') && key !== filterKeys.GPU_COUNT) {
                return false;
            }

            if (key === filterKeys.FLEET && !showFleetFilter) {
                return false;
            }

            return !permanentFilterKeys.includes(key);
        });
    }, [permanentFilters, showFleetFilter, gpuEnabled]);

    const setSearchParamsHandle = ({
        tokens,
        groupBy,
    }: {
        tokens: PropertyFilterProps.Query['tokens'];
        groupBy: MultiselectProps.Options;
    }) => {
        const searchParams = tokensToSearchParams<RequestParamsKeys>(toRangeTokens(tokens));

        groupBy.forEach(({ value }) => searchParams.append(groupByRequestParamName, value as string));

        if (allowUngrouped && !groupBy.length) {
            searchParams.set(groupByRequestParamName, '');
        }

        onChange?.({ ...getOfferFilters(searchParams), group_by: groupBy.map(({ value }) => value as string) });

        if (withSearchParams) setSearchParams(searchParams);
    };

    const onChangePropertyFilterHandle = ({ tokens, operation }: PropertyFilterProps.Query, nextGroupBy = groupBy) => {
        const filteredTokens = tokens.filter((token, tokenIndex) => {
            return (
                multipleChoiceKeys.includes(token.propertyKey as RequestParamsKeys) ||
                !tokens.some((item, index) => token.propertyKey === item.propertyKey && index > tokenIndex)
            );
        });

        nextGroupBy = getGroupBy(nextGroupBy, !filteredTokens.some(isCpuModeToken));
        setSearchParamsHandle({
            tokens: filteredTokens,
            groupBy: nextGroupBy,
        });

        setGroupBy(nextGroupBy);
        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        onChangePropertyFilterHandle(detail);
    };

    const onChangeGpu = (enabled: boolean) => {
        canAutoSelectCpu.current = false;
        const tokens = propertyFilterQuery.tokens.filter((token) => !token.propertyKey?.startsWith('gpu_'));
        if (!enabled) tokens.push({ propertyKey: filterKeys.GPU_COUNT, operator: '=', value: '0' });
        onChangePropertyFilterHandle(
            { ...propertyFilterQuery, tokens },
            enabled && !groupBy.length ? [gpuFilterOption] : groupBy,
        );
    };

    const onChangeGroupBy: MultiselectProps['onChange'] = ({ detail }) => {
        const selectedResource = detail.selectedOptions.some(({ value }) => isResourceGroup(value));

        let tempSelectedOptions: MultiselectProps.Options = detail.selectedOptions;

        if (!selectedResource) {
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
            tokens: toRangeTokens(propertyFilterQuery.tokens),
            arrayFieldKeys: multipleChoiceKeys,
        });

        Object.entries(permanentFilters).forEach(([key, value]) => {
            params[key as RequestParamsKeys] = multipleChoiceKeys.includes(key as RequestParamsKeys) ? [value] : value;
        });

        return params;
    }, [propertyFilterQuery, permanentFilters]);

    const selectedProjectName = useMemo(() => {
        const projectName = filteringRequestParams['project_name'];

        return typeof projectName === 'string' ? projectName : undefined;
    }, [filteringRequestParams]);

    useEffect(() => {
        if (!permanentFilters.project_name && selectedProjectName && selectedProjectName !== rememberedProject) {
            setRememberedProject(selectedProjectName);
        }
    }, [selectedProjectName]);

    const handleLoadItems: PropertyFilterProps['onLoadItems'] = async ({ detail: { filteringProperty, filteringText } }) => {
        setDynamicFilteringOptions([]);

        setFilteringStatusType('loading');

        if (filteringProperty?.key === filterKeys.PROJECT_NAME) {
            await getProjects(
                getTokenAwareNamePatternFilterRequestParams({
                    filteringText,
                    limit,
                    propertyKey: filterKeys.PROJECT_NAME,
                    tokens: propertyFilterQuery.tokens,
                }),
            )
                .unwrap()
                .then(({ data }) =>
                    data.map(({ project_name }) => ({
                        propertyKey: filterKeys.PROJECT_NAME,
                        value: project_name,
                    })),
                )
                .then(setDynamicFilteringOptions);
        }

        const isGpuProperty = [filterKeys.GPU_NAME, filterKeys.GPU_VENDOR, filterKeys.BACKEND].includes(
            filteringProperty?.key as RequestParamsKeys,
        );

        if (loadGpus && isGpuProperty && selectedProjectName) {
            await loadGpus(selectedProjectName);
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

    // Cloudscape can only focus the filter, so typing "Project = " into it lists the projects.
    const openProjectValues = () => {
        if (!propertyFilterRef.current) return;
        propertyFilterRef.current.focus();

        const input = document.activeElement;
        const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;

        if (!(input instanceof HTMLInputElement) || !setInputValue) {
            return;
        }

        setInputValue.call(input, `${projectFilteringProperty.propertyLabel} = `);
        input.dispatchEvent(new Event('input', { bubbles: true }));
    };

    useEffect(() => {
        if (projectNameIsChecked.current || !projectsData) {
            return;
        }

        if (selectedProjectName) {
            projectNameIsChecked.current = true;
            return;
        }

        let cancelled = false;
        const restoreProject = async () => {
            let projectName = projectsData.data.length === 1 ? projectsData.data[0].project_name : undefined;
            if (rememberedProject) {
                try {
                    const project = await getProject({ name: rememberedProject }, false).unwrap();
                    projectName = project.project_name;
                } catch (error) {
                    if (
                        !cancelled &&
                        error &&
                        typeof error === 'object' &&
                        'status' in error &&
                        [403, 404].includes(Number(error.status))
                    ) {
                        setRememberedProject(null);
                    }
                }
            }
            if (cancelled) return;
            projectNameIsChecked.current = true;

            // Otherwise, with several projects, the user picks one.
            if (!projectName) {
                openProjectValues();
                return;
            }

            onChangePropertyFilterHandle({
                tokens: [
                    ...propertyFilterQuery.tokens,
                    { operator: '=', propertyKey: filterKeys.PROJECT_NAME, value: projectName },
                ],
                operation: 'and',
            });
        };
        void restoreProject();
        return () => {
            cancelled = true;
        };
    }, [projectsData, selectedProjectName, rememberedProject, propertyFilterQuery]);

    useEffect(() => {
        const prevProjectName = prevSelectedProjectName.current;
        prevSelectedProjectName.current = selectedProjectName;

        if (!showFleetFilter || prevProjectName === undefined || prevProjectName === selectedProjectName) {
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
        hasCustomFilters,
        propertyFilterRef,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties: filteringPropertiesForShowing,
        groupBy,
        groupByOptions,
        onChangeGroupBy,
        gpuEnabled,
        onChangeGpu,
        canAutoSelectCpu: canAutoSelectCpu.current,
        filteringStatusType,
        handleLoadItems,
    } as const;
};
