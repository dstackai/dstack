import React from 'react';
import { useTranslation } from 'react-i18next';

import { Loader, PropertyFilter, Table } from 'components';
import { TableProps } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useInfiniteScroll } from 'hooks';
import { useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetAllEventsQuery } from 'services/events';

import { useColumnsDefinitions } from './hooks/useColumnDefinitions';
import { useFilters } from './hooks/useFilters';

import styles from '../../Runs/List/styles.module.scss';

type RenderHeaderArgs = {
    refreshAction?: () => void;
    disabledRefresh?: boolean;
};

type EventListProps = Pick<TableProps, 'variant'> & {
    withSearchParams?: boolean;
    renderHeader?: (args: RenderHeaderArgs) => React.ReactNode;
    permanentFilters?: Partial<TEventListFilters>;
};

export const EventList: React.FC<EventListProps> = ({ withSearchParams, permanentFilters, renderHeader, ...props }) => {
    const { t } = useTranslation();

    useBreadcrumbs([
        {
            text: t('navigation.events'),
            href: ROUTES.EVENTS.LIST,
        },
    ]);

    const {
        filteringRequestParams,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        isLoadingFilters,
    } = useFilters({ permanentFilters, withSearchParams });

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IEvent, TEventListRequestParams>({
        useLazyQuery: useLazyGetAllEventsQuery,
        args: { ...filteringRequestParams, limit: DEFAULT_TABLE_PAGE_SIZE },
        skip: isLoadingFilters,

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

    const loading = isLoadingFilters || isLoading;

    return (
        <Table
            {...props}
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            loading={loading}
            loadingText={t('common.loading')}
            stickyHeader={true}
            header={renderHeader?.({ refreshAction: refreshList, disabledRefresh: loading })}
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
