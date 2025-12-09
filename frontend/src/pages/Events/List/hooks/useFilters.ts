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

const targetTypes = ['project', 'user', 'fleet', 'instance', 'run', 'job'];

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

        projectsData?.forEach(({ project_id }) => {
            options.push({
                propertyKey: filterKeys.TARGET_PROJECTS,
                value: project_id,
            });

            options.push({
                propertyKey: filterKeys.WITHIN_PROJECTS,
                value: project_id,
            });
        });

        usersData?.forEach(({ id }) => {
            options.push({
                propertyKey: filterKeys.TARGET_USERS,
                value: id,
            });
        });

        targetTypes?.forEach((targetType) => {
            options.push({
                propertyKey: filterKeys.INCLUDE_TARGET_TYPES,
                value: targetType,
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
            propertyLabel: 'Target Projects',
            groupValuesLabel: 'Project ids',
        },
        {
            key: filterKeys.TARGET_USERS,
            operators: ['='],
            propertyLabel: 'Target Users',
            groupValuesLabel: 'Project ids',
        },
        {
            key: filterKeys.TARGET_FLEETS,
            operators: ['='],
            propertyLabel: 'Target Fleets',
        },
        {
            key: filterKeys.TARGET_INSTANCES,
            operators: ['='],
            propertyLabel: 'Target Instances',
        },
        {
            key: filterKeys.TARGET_RUNS,
            operators: ['='],
            propertyLabel: 'Target Runs',
        },
        {
            key: filterKeys.TARGET_JOBS,
            operators: ['='],
            propertyLabel: 'Target Jobs',
        },

        {
            key: filterKeys.WITHIN_PROJECTS,
            operators: ['='],
            propertyLabel: 'Within Projects',
            groupValuesLabel: 'Project ids',
        },

        {
            key: filterKeys.WITHIN_FLEETS,
            operators: ['='],
            propertyLabel: 'Within Fleets',
        },

        {
            key: filterKeys.WITHIN_RUNS,
            operators: ['='],
            propertyLabel: 'Within Runs',
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
