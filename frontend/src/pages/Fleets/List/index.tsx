import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Header, Pagination, Table } from 'components';
import { useProjectDropdown } from 'layouts/AppLayout/hooks';

import { useCollection } from 'hooks';
import { useGetFleetsQuery } from 'services/fleet';

import { useColumnsDefinitions, useEmptyMessages } from './hooks';

import { TFleetInstance } from './types';

export const FleetsList: React.FC = () => {
    const { t } = useTranslation();
    const { selectedProject } = useProjectDropdown();

    const { data, isLoading } = useGetFleetsQuery({ projectName: selectedProject ?? '' });

    const { columns } = useColumnsDefinitions();
    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages();

    const fleetInstances = useMemo<TFleetInstance[]>(() => {
        if (!data) return [];

        return data.reduce<TFleetInstance[]>((acc, item, index) => {
            if (!item.instances.length) {
                acc.push({ fleetName: item.name });

                return acc;
            }

            item.instances.forEach((instance) => {
                acc.push({ fleetName: item.name, ...instance });
            });

            if (index === 1) {
                acc.push({ fleetName: 'Test' });
            }

            return acc;
        }, []);
    }, [data]);

    const { items, collectionProps, paginationProps } = useCollection<TFleetInstance[]>(fleetInstances, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            stickyHeader={true}
            header={<Header variant="awsui-h1-sticky">{t('navigation.fleets')}</Header>}
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
        />
    );
};
