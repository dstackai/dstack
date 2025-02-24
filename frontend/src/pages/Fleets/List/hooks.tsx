import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { Button, ListEmptyMessage, NavigateLink, StatusIndicator, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { useProjectFilter } from 'hooks/useProjectFilter';
import { getFleetInstancesLinkText, getFleetPrice, getFleetStatusIconType } from 'libs/fleet';
import { ROUTES } from 'routes';

export const useEmptyMessages = ({
    clearFilters,
    isDisabledClearFilter,
}: {
    clearFilters?: () => void;
    isDisabledClearFilter?: boolean;
}) => {
    const { t } = useTranslation();

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('fleets.empty_message_title')} message={t('fleets.empty_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilters}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilters, isDisabledClearFilter]);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('fleets.nomatch_message_title')} message={t('fleets.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilters}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilters, isDisabledClearFilter]);

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
                <NavigateLink href={ROUTES.INSTANCES.LIST + `?fleetId=${item.id}`}>
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

export const useFilters = (localStorePrefix = 'fleet-list-page') => {
    const [onlyActive, setOnlyActive] = useLocalStorageState<boolean>(`${localStorePrefix}-is-active`, true);
    const { selectedProject, setSelectedProject, projectOptions } = useProjectFilter({ localStorePrefix });

    const clearFilters = () => {
        setOnlyActive(false);
        setSelectedProject(null);
    };

    const isDisabledClearFilter = !selectedProject && !onlyActive;

    return {
        projectOptions,
        selectedProject,
        setSelectedProject,
        onlyActive,
        setOnlyActive,
        clearFilters,
        isDisabledClearFilter,
    } as const;
};
