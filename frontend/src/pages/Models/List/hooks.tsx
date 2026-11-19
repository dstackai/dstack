import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { format } from 'date-fns';

import type { PropertyFilterProps, ToggleProps } from 'components';
import { Button, ListEmptyMessage, NavigateLink, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useLocalStorageState } from 'hooks';
import {
    EMPTY_QUERY,
    getNamePatternFilterRequestParams,
    requestParamsToTokens,
    tokensToRequestParams,
    tokensToSearchParams,
} from 'libs/filters';
import { ROUTES } from 'routes';
import { useLazyGetProjectsQuery } from 'services/project';
import { useLazyGetUserListQuery } from 'services/user';

import { ModelStatus } from '../components/ModelStatus';

import { IModelExtended, TModelsFilters } from './types';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<IModelExtended>[] = [
        {
            id: 'model_name',
            header: t('models.model_name'),
            cell: (item) => {
                return (
                    <NavigateLink href={ROUTES.MODELS.DETAILS.FORMAT(item.project_name, item.name)}>{item.name}</NavigateLink>
                );
            },
        },
        {
            id: 'status',
            header: `${t('models.status')}`,
            cell: (item) => <ModelStatus model={item} />,
        },
        {
            id: 'project',
            header: `${t('models.project')}`,
            cell: (item) => (
                <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(item.project_name)}>{item.project_name}</NavigateLink>
            ),
        },
        {
            id: 'run',
            header: `${t('models.run')}`,
            cell: (item) =>
                item.run ? (
                    <NavigateLink href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(item.project_name, item.run.id)}>
                        {item.run.run_name}
                    </NavigateLink>
                ) : (
                    '-'
                ),
        },
        {
            id: 'resources',
            header: `${t('models.resources')}`,
            cell: (item) => item.run?.resources ?? '-',
        },
        {
            id: 'price',
            header: `${t('models.price')}`,
            cell: (item) => (item.run?.price ? `$${item.run.price}` : '-'),
        },
        {
            id: 'submitted_at',
            header: `${t('models.submitted_at')}`,
            cell: (item) => (item.run ? format(new Date(item.run.submitted_at), DATE_TIME_FORMAT) : '-'),
        },
        {
            id: 'user',
            header: `${t('models.user')}`,
            cell: (item) =>
                item.run ? <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(item.run.user)}>{item.run.user}</NavigateLink> : '-',
        },
        {
            id: 'repository',
            header: `${t('models.repository')}`,
            cell: (item) => item.run?.repository ?? '-',
        },
        {
            id: 'backend',
            header: `${t('models.backend')}`,
            cell: (item) => item.run?.backend ?? '-',
        },
    ];

    return { columns } as const;
};

export const useEmptyMessages = ({
    clearFilter,
    isDisabledClearFilter,
}: {
    clearFilter?: () => void;
    isDisabledClearFilter?: boolean;
}) => {
    const { t } = useTranslation();

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('models.empty_message_title')} message={t('models.empty_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilter, isDisabledClearFilter]);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('models.nomatch_message_title')} message={t('models.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilter, isDisabledClearFilter]);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};

type RequestParamsKeys = keyof TModelsFilters;

const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    USER_NAME: 'username',
};

const limit = 100;

export const useFilters = () => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [onlyActive, setOnlyActive] = useLocalStorageState('model-list-filter-only-active', true);
    const [filteringOptions, setFilteringOptions] = useState<PropertyFilterProps.FilteringOption[]>([]);
    const [filteringStatusType, setFilteringStatusType] = useState<PropertyFilterProps.StatusType | undefined>();
    const [getProjects] = useLazyGetProjectsQuery();
    const [getUsers] = useLazyGetUserListQuery();

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() =>
        requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys }),
    );

    const clearFilter = () => {
        setSearchParams({});
        setPropertyFilterQuery(EMPTY_QUERY);
    };

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
            groupValuesLabel: 'User values',
        },
    ];

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        const { tokens, operation } = detail;

        const filteredTokens = tokens.filter((token, tokenIndex) => {
            return !tokens.some((item, index) => token.propertyKey === item.propertyKey && index > tokenIndex);
        });

        setSearchParams(tokensToSearchParams<RequestParamsKeys>(filteredTokens));

        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const onChangeOnlyActive: ToggleProps['onChange'] = ({ detail }) => {
        setOnlyActive(detail.checked);
    };

    const filteringRequestParams = useMemo(() => {
        return tokensToRequestParams<RequestParamsKeys>({
            tokens: propertyFilterQuery.tokens,
        }) as TModelsFilters;
    }, [propertyFilterQuery]);

    const handleLoadItems: PropertyFilterProps['onLoadItems'] = async ({ detail: { filteringProperty, filteringText } }) => {
        setFilteringOptions([]);

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
                .then(setFilteringOptions);
        }

        if (filteringProperty?.key === filterKeys.USER_NAME) {
            await getUsers(getNamePatternFilterRequestParams(filteringText, limit))
                .unwrap()
                .then(({ data }) =>
                    data.map(({ username }) => ({
                        propertyKey: filterKeys.USER_NAME,
                        value: username,
                    })),
                )
                .then(setFilteringOptions);
        }

        setFilteringStatusType(undefined);
    };

    return {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        onlyActive,
        onChangeOnlyActive,
        filteringStatusType,
        handleLoadItems,
    } as const;
};
