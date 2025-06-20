import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { format } from 'date-fns';
import { ToggleProps } from '@cloudscape-design/components';

import type { PropertyFilterProps } from 'components';
import { Button, ListEmptyMessage, NavigateLink, StatusIndicator, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useProjectFilter } from 'hooks/useProjectFilter';
import { EMPTY_QUERY, requestParamsToTokens, tokensToRequestParams, tokensToSearchParams } from 'libs/filters';
import { getFleetInstancesLinkText, getFleetPrice, getFleetStatusIconType } from 'libs/fleet';
import { ROUTES } from 'routes';

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
            <ListEmptyMessage title={t('fleets.empty_message_title')} message={t('fleets.empty_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilter, isDisabledClearFilter]);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('fleets.nomatch_message_title')} message={t('fleets.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilter, isDisabledClearFilter]);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<IFleet>[] = [
        {
            id: 'fleet_name',
            header: t('fleets.fleet'),
            cell: (item) => (
                <NavigateLink href={ROUTES.FLEETS.DETAILS.FORMAT(item.project_name, item.id)}>{item.name}</NavigateLink>
            ),
        },
        {
            id: 'status',
            header: t('fleets.instances.status'),
            cell: (item) => (
                <StatusIndicator type={getFleetStatusIconType(item.status)}>
                    {t(`fleets.statuses.${item.status}`)}
                </StatusIndicator>
            ),
        },
        {
            id: 'project',
            header: t('fleets.instances.project'),
            cell: (item) => (
                <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(item.project_name)}>{item.project_name}</NavigateLink>
            ),
        },
        {
            id: 'instances',
            header: t('fleets.instances.title'),
            cell: (item) => (
                <NavigateLink href={ROUTES.INSTANCES.LIST + `?fleet_ids=${item.id}`}>
                    {getFleetInstancesLinkText(item)}
                </NavigateLink>
            ),
        },
        {
            id: 'started',
            header: t('fleets.instances.started'),
            cell: (item) => format(new Date(item.created_at), DATE_TIME_FORMAT),
        },
        {
            id: 'price',
            header: t('fleets.instances.price'),
            cell: (item) => {
                const price = getFleetPrice(item);

                if (typeof price === 'number') return `$${price}`;

                return '-';
            },
        },
    ];

    return { columns } as const;
};

type RequestParamsKeys = keyof Pick<TFleetListRequestParams, 'only_active' | 'project_name'>;

const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
};

export const useFilters = (localStorePrefix = 'fleet-list-page') => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [onlyActive, setOnlyActive] = useState(() => searchParams.get('only_active') === 'true');
    const { projectOptions } = useProjectFilter({ localStorePrefix });

    const [propertyFilterQuery, setPropertyFilterQuery] = useState<PropertyFilterProps.Query>(() =>
        requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys }),
    );

    const clearFilter = () => {
        setSearchParams({});
        setOnlyActive(false);
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

        return options;
    }, [projectOptions]);

    const filteringProperties = [
        {
            key: filterKeys.PROJECT_NAME,
            operators: ['='],
            propertyLabel: 'Project',
            groupValuesLabel: 'Project values',
        },
    ];

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        const { tokens, operation } = detail;

        const filteredTokens = tokens.filter((token, tokenIndex) => {
            return !tokens.some((item, index) => token.propertyKey === item.propertyKey && index > tokenIndex);
        });

        setSearchParams(tokensToSearchParams<RequestParamsKeys>(filteredTokens, onlyActive));

        setPropertyFilterQuery({
            operation,
            tokens: filteredTokens,
        });
    };

    const onChangeOnlyActive: ToggleProps['onChange'] = ({ detail }) => {
        setOnlyActive(detail.checked);

        setSearchParams(tokensToSearchParams<RequestParamsKeys>(propertyFilterQuery.tokens, detail.checked));
    };

    const filteringRequestParams = useMemo(() => {
        const params = tokensToRequestParams<RequestParamsKeys>({
            tokens: propertyFilterQuery.tokens,
        });

        return {
            ...params,
            only_active: onlyActive,
        } as Partial<TFleetListRequestParams>;
    }, [propertyFilterQuery, onlyActive]);

    const isDisabledClearFilter = !propertyFilterQuery.tokens.length && !onlyActive;

    return {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        onlyActive,
        onChangeOnlyActive,
        isDisabledClearFilter,
    } as const;
};
