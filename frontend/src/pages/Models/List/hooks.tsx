import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { format } from 'date-fns';

import type { PropertyFilterProps } from 'components';
import { Button, ListEmptyMessage, NavigateLink, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useProjectFilter } from 'hooks/useProjectFilter';
import { EMPTY_QUERY, requestParamsToTokens, tokensToRequestParams, tokensToSearchParams } from 'libs/filters';
import { ROUTES } from 'routes';
import { useGetUserListQuery } from 'services/user';

import { getModelGateway } from '../helpers';

import { IModelExtended } from './types';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<IModelExtended>[] = [
        {
            id: 'model_name',
            header: t('models.model_name'),
            cell: (item) => {
                return (
                    <NavigateLink href={ROUTES.MODELS.DETAILS.FORMAT(item.project_name, item.run_name)}>
                        {item.name}
                    </NavigateLink>
                );
            },
        },
        {
            id: 'type',
            header: `${t('models.type')}`,
            cell: (item) => item.type,
        },
        {
            id: 'url',
            header: `${t('models.url')}`,
            cell: (item) => getModelGateway(item.base_url),
        },
        {
            id: 'run',
            header: `${t('models.run')}`,
            cell: (item) => (
                <NavigateLink
                    href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(item.project_name, item.run_name ?? 'No run name')}
                >
                    {item.run_name}
                </NavigateLink>
            ),
        },
        {
            id: 'resources',
            header: `${t('models.resources')}`,
            cell: (item) => item.resources,
        },
        {
            id: 'price',
            header: `${t('models.price')}`,
            cell: (item) => (item.price ? `$${item.price}` : null),
        },
        {
            id: 'submitted_at',
            header: `${t('models.submitted_at')}`,
            cell: (item) => format(new Date(item.submitted_at), DATE_TIME_FORMAT),
        },
        {
            id: 'user',
            header: `${t('models.user')}`,
            cell: (item) => <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(item.user)}>{item.user}</NavigateLink>,
        },
        {
            id: 'repository',
            header: `${t('models.repository')}`,
            cell: (item) => item.repository,
        },
        {
            id: 'backend',
            header: `${t('models.backend')}`,
            cell: (item) => item.backend,
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

type RequestParamsKeys = keyof Pick<TRunsRequestParams, 'project_name' | 'username'>;

const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    USER_NAME: 'username',
};

export const useFilters = (localStorePrefix = 'models-list-page') => {
    const [searchParams, setSearchParams] = useSearchParams();
    const { projectOptions } = useProjectFilter({ localStorePrefix });
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

        setSearchParams(tokensToSearchParams<RequestParamsKeys>(filteredTokens));

        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const filteringRequestParams = useMemo(() => {
        return tokensToRequestParams<RequestParamsKeys>({
            tokens: propertyFilterQuery.tokens,
        }) as Partial<TRunsRequestParams>;
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
