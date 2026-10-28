import React from 'react';
import { useTranslation } from 'react-i18next';

import { DateRangePicker, Loader, PropertyFilter, Table } from 'components';
import { TableProps } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useInfiniteScroll } from 'hooks';
import { useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetAllEventsQuery } from 'services/events';

import { useColumnsDefinitions } from './hooks/useColumnDefinitions';
import { useEventsOrder } from './hooks/useEventsOrder';
import { useFilters } from './hooks/useFilters';
import { relativeOptions, useTimeRange } from './hooks/useTimeRange';

import styles from './styles.module.scss';

type RenderHeaderArgs = {
    refreshAction?: () => void;
    disabledRefresh?: boolean;
    ascending: boolean;
};

type EventListProps = Pick<TableProps, 'variant'> & {
    withSearchParams?: boolean;
    renderHeader?: (args: RenderHeaderArgs) => React.ReactNode;
    permanentFilters?: Partial<TEventListFilters>;
    showFilters?: boolean;
};

export const EventList: React.FC<EventListProps> = ({
    withSearchParams,
    permanentFilters,
    renderHeader,
    showFilters = true,
    ...props
}) => {
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
        filteringStatusType,
        handleLoadItems,
    } = useFilters({ permanentFilters, withSearchParams });

    const { ascending, sortingProps } = useEventsOrder({ withSearchParams });

    const {
        timeRange,
        onChangeTimeRange,
        isValidRange,
        refreshRelativeTimeRange,
        requestParams: timeRangeRequestParams,
        isPastEnd,
    } = useTimeRange({ withSearchParams, ascending });

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IEvent, TEventListRequestParams>({
        useLazyQuery: useLazyGetAllEventsQuery,
        args: { ...filteringRequestParams, ...timeRangeRequestParams, limit: DEFAULT_TABLE_PAGE_SIZE },
        isPastEnd,

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

    const refreshAction = () => {
        if (!refreshRelativeTimeRange()) {
            refreshList();
        }
    };

    const loading = isLoading;

    return (
        <Table
            {...props}
            {...collectionProps}
            {...sortingProps}
            columnDefinitions={columns}
            items={items}
            loading={loading}
            loadingText={t('common.loading')}
            stickyHeader={true}
            header={renderHeader?.({ refreshAction, disabledRefresh: loading, ascending })}
            filter={
                showFilters && (
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
                                    enteredTextLabel: (value) => `Use: ${value}`,
                                }}
                                filteringOptions={filteringOptions}
                                filteringProperties={filteringProperties}
                                filteringStatusType={filteringStatusType}
                                onLoadItems={handleLoadItems}
                            />
                        </div>

                        <DateRangePicker
                            value={timeRange}
                            onChange={onChangeTimeRange}
                            relativeOptions={relativeOptions}
                            isValidRange={isValidRange}
                            placeholder={t('events.time_range_placeholder')}
                            expandToViewport
                        />
                    </div>
                )
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
