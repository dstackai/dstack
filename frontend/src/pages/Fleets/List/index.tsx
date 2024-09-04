import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, FormField, Header, Pagination, SelectCSD, Table, Toggle } from 'components';
import { useProjectDropdown } from 'layouts/AppLayout/hooks';

import { useCollection } from 'hooks';
import { useGetFleetsQuery } from 'services/fleet';

import { useColumnsDefinitions, useEmptyMessages, useFilters } from './hooks';

import { TFleetInstance } from './types';

import styles from './styles.module.scss';

export const FleetsList: React.FC = () => {
    const { t } = useTranslation();
    const { selectedProject } = useProjectDropdown();

    const { data, isLoading } = useGetFleetsQuery({ projectName: selectedProject ?? '' });

    const { columns } = useColumnsDefinitions();
    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages();

    const {
        fleetOptions,
        selectedFleet,
        setSelectedFleet,
        setOnlyActive,
        onlyActive,
        isDisabledClearFilter,
        clearFilters,
        filteringFunction,
    } = useFilters({ fleets: data });

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
            filteringFunction,
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
            filter={
                <div className={styles.filters}>
                    <div className={styles.select}>
                        <FormField label={t('fleets.fleet')}>
                            <SelectCSD
                                disabled={!fleetOptions?.length}
                                options={fleetOptions}
                                selectedOption={selectedFleet}
                                onChange={(event) => {
                                    setSelectedFleet(event.detail.selectedOption);
                                }}
                                placeholder={t('fleets.fleet_placeholder')}
                                expandToViewport={true}
                                filteringType="auto"
                            />
                        </FormField>
                    </div>

                    <div className={styles.activeOnly}>
                        <Toggle
                            disabled={!fleetInstances.length}
                            onChange={({ detail }) => setOnlyActive(detail.checked)}
                            checked={onlyActive}
                        >
                            {t('fleets.active_only')}
                        </Toggle>
                    </div>

                    <div className={styles.clear}>
                        <Button formAction="none" onClick={clearFilters} disabled={isDisabledClearFilter}>
                            {t('common.clearFilter')}
                        </Button>
                    </div>
                </div>
            }
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
        />
    );
};
