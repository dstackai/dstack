import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Header, Loader, PropertyFilter, SpaceBetween, Table } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useInfiniteScroll } from 'hooks';
import { useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetAllEventsQuery } from 'services/events';

import { useColumnsDefinitions } from './hooks/useColumnDefinitions';
import { useFilters } from './hooks/useFilters';

import styles from '../../Runs/List/styles.module.scss';

export const EventList = () => {
    const { t } = useTranslation();

    useBreadcrumbs([
        {
            text: t('navigation.events'),
            href: ROUTES.EVENTS.LIST,
        },
    ]);

    const { filteringRequestParams, propertyFilterQuery, onChangePropertyFilter, filteringOptions, filteringProperties } =
        useFilters();

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IEvent, TEventListRequestParams>({
        useLazyQuery: useLazyGetAllEventsQuery,
        args: { ...filteringRequestParams, limit: DEFAULT_TABLE_PAGE_SIZE },

        getPaginationParams: (lastEvent) => ({
            prev_recorded_at: lastEvent.recorded_at,
            prev_id: lastEvent.id,
        }),
    });

    const { items, collectionProps } = useCollection<IEvent>(data, {
        filtering: {
            // empty: renderEmptyMessage(),
            // noMatch: renderNoMatchMessage(),
        },
        selection: {},
    });

    const { columns } = useColumnsDefinitions();

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            stickyHeader={true}
            selectionType="multi"
            header={
                <Header
                    variant="awsui-h1-sticky"
                    actions={
                        <SpaceBetween size="xs" direction="horizontal">
                            <Button
                                iconName="refresh"
                                disabled={isLoading}
                                ariaLabel={t('common.refresh')}
                                onClick={refreshList}
                            />
                        </SpaceBetween>
                    }
                >
                    {t('navigation.events')}
                </Header>
            }
            filter={
                <div className={styles.selectFilters}>
                    <div className={styles.propertyFilter}>
                        <PropertyFilter
                            query={propertyFilterQuery}
                            onChange={onChangePropertyFilter}
                            expandToViewport
                            hideOperations
                            i18nStrings={{
                                clearFiltersText: t('common.clearFilter'),
                                filteringAriaLabel: t('projects.run.filter_property_placeholder'),
                                filteringPlaceholder: t('projects.run.filter_property_placeholder'),
                                operationAndText: 'and',
                            }}
                            filteringOptions={filteringOptions}
                            filteringProperties={filteringProperties}
                        />
                    </div>
                </div>
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
