import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { ListEmptyMessage, StatusIndicator, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { getStatusIconType } from 'libs/fleet';

import { SelectCSDProps } from '../../../components';
import { useLocalStorageState } from '../../../hooks/useLocalStorageState';

import { TFleetInstance } from './types';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<TFleetInstance>[] = [
        {
            id: 'fleet',
            header: t('fleets.fleet'),
            cell: (item) =>
                // <NavigateLink href={ROUTES.FLEETS.DETAILS.FORMAT(item.project_name, item.name)}>{item.name}</NavigateLink>
                item.fleetName,
        },
        {
            id: 'instance',
            header: `${t('fleets.instances.instance_name')}`,
            cell: (item) => item?.instance_type?.name,
        },
        {
            id: 'backend',
            header: `${t('fleets.instances.backend')}`,
            cell: (item) => item?.backend,
        },
        {
            id: 'resources',
            header: `${t('fleets.instances.resources')}`,
            cell: (item) => item?.instance_type?.resources.description,
        },
        {
            id: 'price',
            header: `${t('fleets.instances.price')}`,
            cell: (item) => item?.price && `$${item.price}`,
        },
        {
            id: 'created',
            header: t('fleets.instances.created'),
            cell: (item) => item?.created && format(new Date(item.created), DATE_TIME_FORMAT),
        },
        {
            id: 'status',
            header: `${t('fleets.instances.status')}`,
            cell: (item) =>
                item?.status && (
                    <StatusIndicator type={getStatusIconType(item.status)}>
                        {t(`fleets.instances.statuses.${item.status}`)}
                    </StatusIndicator>
                ),
        },
    ];

    return { columns } as const;
};

export const useEmptyMessages = () => {
    const { t } = useTranslation();

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        return <ListEmptyMessage title={t('fleets.empty_message_title')} message={t('fleets.empty_message_text')} />;
    }, []);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return <ListEmptyMessage title={t('fleets.nomatch_message_title')} message={t('fleets.nomatch_message_text')} />;
    }, []);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};

export const useFilters = ({ fleets }: { fleets?: IFleet[] }) => {
    const [onlyActive, setOnlyActive] = useLocalStorageState<boolean>('administration-fleet-list-is-active', false);
    const [selectedFleet, setSelectedFleet] = useState<SelectCSDProps.Option | null>(null);

    const fleetOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!fleets?.length) return [];

        return fleets.map((fleet) => ({ label: fleet.name, value: fleet.name }));
    }, [fleets]);

    const clearFilters = () => {
        setOnlyActive(false);
        setSelectedFleet(null);
    };

    const filteringFunction = useCallback<(instance: TFleetInstance) => boolean>(
        (instance: TFleetInstance) => {
            let isMatch = true;

            if (selectedFleet) {
                isMatch = isMatch && instance.fleetName === selectedFleet.value;
            }

            if (onlyActive) {
                isMatch =
                    isMatch &&
                    ['creating', 'starting', 'provisioning', 'terminating', 'busy', 'idle'].includes(instance.status ?? '');
            }

            return isMatch;
        },
        [onlyActive, selectedFleet],
    );

    const isDisabledClearFilter = !selectedFleet && !onlyActive;

    return {
        onlyActive,
        setOnlyActive,
        selectedFleet,
        setSelectedFleet,
        fleetOptions,
        isDisabledClearFilter,
        clearFilters,
        filteringFunction,
    } as const;
};
