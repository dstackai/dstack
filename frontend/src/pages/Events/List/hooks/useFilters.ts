import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { PropertyFilterProps } from 'components';

import { EMPTY_QUERY, requestParamsToTokens, tokensToRequestParams, tokensToSearchParams } from 'libs/filters';
import { useGetProjectsQuery } from 'services/project';
import { useGetUserListQuery } from 'services/user';

import { filterLastElementByPrefix } from '../helpers';

type RequestParamsKeys = keyof Pick<
    TEventListRequestParams,
    | 'target_projects'
    | 'target_users'
    | 'target_fleets'
    | 'target_instances'
    | 'target_runs'
    | 'target_jobs'
    | 'within_projects'
    | 'within_fleets'
    | 'within_runs'
    | 'include_target_types'
    | 'actors'
>;

const filterKeys: Record<string, RequestParamsKeys> = {
    TARGET_PROJECTS: 'target_projects',
    TARGET_USERS: 'target_users',
    TARGET_FLEETS: 'target_fleets',
    TARGET_INSTANCES: 'target_instances',
    TARGET_RUNS: 'target_runs',
    TARGET_JOBS: 'target_jobs',
    WITHIN_PROJECTS: 'within_projects',
    WITHIN_FLEETS: 'within_fleets',
    WITHIN_RUNS: 'within_runs',
    INCLUDE_TARGET_TYPES: 'include_target_types',
    ACTORS: 'actors',
};

const onlyOneFilterGroupPrefixes = ['target_', 'within_'];

const multipleChoiseKeys: RequestParamsKeys[] = [
    'target_projects',
    'target_users',
    'target_fleets',
    'target_instances',
    'target_runs',
    'target_jobs',
    'within_projects',
    'within_fleets',
    'within_runs',
    'include_target_types',
    'actors',
];

const targetTypes = [
    { label: 'Project', value: 'project' },
    { label: 'User', value: 'user' },
    { label: 'Fleet', value: 'fleet' },
    { label: 'Instance', value: 'instance' },
    { label: 'Run', value: 'run' },
    { label: 'Job', value: 'job' },
];

export const useFilters = () => {
    const [searchParams, setSearchParams] = useSearchParams();
    const { data: projectsData } = useGetProjectsQuery();
    const { data: usersData } = useGetUserListQuery();

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() =>
        requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys }),
    );

    const clearFilter = () => {
        setSearchParams({});
        setPropertyFilterQuery(EMPTY_QUERY);
    };

    const filteringOptions = useMemo(() => {
        const options: PropertyFilterProps.FilteringOption[] = [];

        projectsData?.forEach(({ project_name }) => {
            options.push({
                propertyKey: filterKeys.TARGET_PROJECTS,
                value: project_name,
            });

            options.push({
                propertyKey: filterKeys.WITHIN_PROJECTS,
                value: project_name,
            });
        });

        usersData?.forEach(({ username }) => {
            options.push({
                propertyKey: filterKeys.TARGET_USERS,
                value: username,
            });

            options.push({
                propertyKey: filterKeys.ACTORS,
                value: username,
            });
        });

        targetTypes?.forEach((targetType) => {
            options.push({
                propertyKey: filterKeys.INCLUDE_TARGET_TYPES,
                value: targetType.label,
            });
        });

        return options;
    }, [projectsData, usersData]);

    const setSearchParamsHandle = ({ tokens }: { tokens: PropertyFilterProps.Query['tokens'] }) => {
        const searchParams = tokensToSearchParams<RequestParamsKeys>(tokens);

        setSearchParams(searchParams);
    };

    const filteringProperties = [
        {
            key: filterKeys.TARGET_PROJECTS,
            operators: ['='],
            propertyLabel: 'Target projects',
            groupValuesLabel: 'Project ids',
        },
        {
            key: filterKeys.TARGET_USERS,
            operators: ['='],
            propertyLabel: 'Target users',
            groupValuesLabel: 'Project ids',
        },
        {
            key: filterKeys.TARGET_FLEETS,
            operators: ['='],
            propertyLabel: 'Target fleets',
        },
        {
            key: filterKeys.TARGET_INSTANCES,
            operators: ['='],
            propertyLabel: 'Target instances',
        },
        {
            key: filterKeys.TARGET_RUNS,
            operators: ['='],
            propertyLabel: 'Target runs',
        },
        {
            key: filterKeys.TARGET_JOBS,
            operators: ['='],
            propertyLabel: 'Target jobs',
        },

        {
            key: filterKeys.WITHIN_PROJECTS,
            operators: ['='],
            propertyLabel: 'Within projects',
            groupValuesLabel: 'Project ids',
        },

        {
            key: filterKeys.WITHIN_FLEETS,
            operators: ['='],
            propertyLabel: 'Within fleets',
        },

        {
            key: filterKeys.WITHIN_RUNS,
            operators: ['='],
            propertyLabel: 'Within runs',
        },

        {
            key: filterKeys.INCLUDE_TARGET_TYPES,
            operators: ['='],
            propertyLabel: 'Target types',
            groupValuesLabel: 'Target type values',
        },

        {
            key: filterKeys.ACTORS,
            operators: ['='],
            propertyLabel: 'Actors',
        },
    ];

    const onChangePropertyFilterHandle = ({ tokens, operation }: PropertyFilterProps.Query) => {
        let filteredTokens = [...tokens];

        onlyOneFilterGroupPrefixes.forEach((prefix) => {
            try {
                filteredTokens = filterLastElementByPrefix(filteredTokens, prefix);
            } catch (_) {
                console.error(_);
            }
        });

        setSearchParamsHandle({ tokens: filteredTokens });

        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        onChangePropertyFilterHandle(detail);
    };

    const filteringRequestParams = useMemo(() => {
        const params = tokensToRequestParams<RequestParamsKeys>({
            tokens: propertyFilterQuery.tokens,
            arrayFieldKeys: multipleChoiseKeys,
        });

        const mappedFields = {
            ...(params[filterKeys.TARGET_PROJECTS] && Array.isArray(params[filterKeys.TARGET_PROJECTS])
                ? {
                      [filterKeys.TARGET_PROJECTS]: params[filterKeys.TARGET_PROJECTS]?.map(
                          (name: string) => projectsData?.find(({ project_name }) => project_name === name)?.['project_id'],
                      ),
                  }
                : {}),
            ...(params[filterKeys.WITHIN_PROJECTS] && Array.isArray(params[filterKeys.WITHIN_PROJECTS])
                ? {
                      [filterKeys.WITHIN_PROJECTS]: params[filterKeys.WITHIN_PROJECTS]?.map(
                          (name: string) => projectsData?.find(({ project_name }) => project_name === name)?.['project_id'],
                      ),
                  }
                : {}),

            ...(params[filterKeys.TARGET_USERS] && Array.isArray(params[filterKeys.TARGET_USERS])
                ? {
                      [filterKeys.TARGET_USERS]: params[filterKeys.TARGET_USERS]?.map(
                          (name: string) => usersData?.find(({ username }) => username === name)?.['id'],
                      ),
                  }
                : {}),

            ...(params[filterKeys.ACTORS] && Array.isArray(params[filterKeys.ACTORS])
                ? {
                      [filterKeys.ACTORS]: params[filterKeys.ACTORS]?.map(
                          (name: string) => usersData?.find(({ username }) => username === name)?.['id'],
                      ),
                  }
                : {}),

            ...(params[filterKeys.INCLUDE_TARGET_TYPES] && Array.isArray(params[filterKeys.INCLUDE_TARGET_TYPES])
                ? {
                      [filterKeys.INCLUDE_TARGET_TYPES]: params[filterKeys.INCLUDE_TARGET_TYPES]?.map(
                          (selectedLabel: string) => targetTypes?.find(({ label }) => label === selectedLabel)?.['value'],
                      ),
                  }
                : {}),
        };

        return {
            ...params,
            ...mappedFields,
        } as Partial<TRunsRequestParams>;
    }, [propertyFilterQuery, usersData, projectsData]);

    return {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
    } as const;
};
