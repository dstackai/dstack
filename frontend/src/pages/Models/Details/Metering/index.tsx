import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { TableProps } from 'components';
import { Alert, DateRangePicker, Header, ListEmptyMessage, PropertyFilter, SegmentedControl, Table } from 'components';

import { useCollection } from 'hooks';
import { getServerError } from 'libs';
import { useGetMeteringQuery } from 'services/metering';

import {
    compareMeteringPeriods,
    DEFAULT_PERIOD,
    formatMeteringPeriod,
    getMeteringRequestParams,
    getMeteringTotal,
    getUserOptionsRequestParams,
    RELATIVE_OPTIONS,
    TMeteringPeriod,
} from './helpers';
import { useFilteringOptions, useFilters, useTimeRange, useUserFilteringOptions } from './hooks';

import { IModelExtended } from '../../List/types';

import styles from './styles.module.scss';

// The token counts of a row and of the total row
const TOKENS = ['input_tokens', 'cached_input_tokens', 'output_tokens'] as const;

export const ModelMetering: React.FC<{ model: IModelExtended }> = ({ model }) => {
    const { t } = useTranslation();
    const [period, setPeriod] = useState<TMeteringPeriod>(DEFAULT_PERIOD);
    const { timeRange, onChangeTimeRange, isValidRange } = useTimeRange(period);
    const { filteringRequestParams, propertyFilterQuery, onChangePropertyFilter, filteringProperties } = useFilters();

    const [requestParams, userOptionsRequestParams] = useMemo(() => {
        const request = { model, timeRange, period, filters: filteringRequestParams, now: new Date() };

        return [getMeteringRequestParams(request), getUserOptionsRequestParams(request)];
    }, [model, timeRange, period, filteringRequestParams]);

    const { currentData, isFetching, error } = useGetMeteringQuery(requestParams);

    // A failed request shows its error, not the rows of an earlier answer
    const rows = useMemo(() => (error ? [] : (currentData ?? [])), [currentData, error]);
    // The total of the rows, so it follows the filter, the time range and the period.
    // The API returns every row of a request, so the browser sums them
    const total = useMemo(() => getMeteringTotal(rows), [rows]);

    const filteringOptions = useFilteringOptions(currentData);
    const { userFilteringOptions, filteringStatusType, handleLoadItems } = useUserFilteringOptions(userOptionsRequestParams);

    // The total row's cells look like the column headers
    const renderCell = (item: IMeteringRow, content: string) =>
        item === total ? <span className={styles.total}>{content}</span> : content;

    const columns: TableProps.ColumnDefinition<IMeteringRow>[] = [
        {
            id: 'period',
            header: t(`models.metering.${period}_utc`),
            cell: (item) => renderCell(item, item === total ? t('models.metering.total') : formatMeteringPeriod(item)),
            sortingComparator: compareMeteringPeriods,
        },
        {
            id: 'project',
            header: t('models.project'),
            cell: (item) => item.project_name,
        },
        ...TOKENS.map((tokens) => ({
            id: tokens,
            header: t(`models.metering.${tokens}`),
            cell: (item: IMeteringRow) => renderCell(item, item[tokens].toLocaleString()),
            sortingField: tokens,
        })),
    ];

    const { items, collectionProps } = useCollection<IMeteringRow>(rows, {
        filtering: {
            empty: error ? (
                <Alert type="error">{t('common.server_error', { error: getServerError(error) })}</Alert>
            ) : (
                <ListEmptyMessage
                    title={t('models.metering.empty_message_title')}
                    message={t('models.metering.empty_message_text')}
                />
            ),
        },
        sorting: {
            defaultState: { sortingColumn: columns[0], isDescending: true },
        },
    });

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            // The total is the last row whatever the sorting is: the collection sorts the rows above it
            items={rows.length ? [...items, total] : items}
            loading={isFetching}
            loadingText={t('common.loading')}
            header={<Header>{t('models.metering.tokens')}</Header>}
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
                                enteredTextLabel: (value) => `Use: ${value}`,
                            }}
                            filteringOptions={[...filteringOptions, ...userFilteringOptions]}
                            filteringProperties={filteringProperties}
                            filteringStatusType={filteringStatusType}
                            onLoadItems={handleLoadItems}
                        />
                    </div>

                    <DateRangePicker
                        // By month, the picker picks months, and its values have another form than by day.
                        // So each period gets a picker of its own
                        key={period}
                        value={timeRange}
                        onChange={onChangeTimeRange}
                        relativeOptions={RELATIVE_OPTIONS[period]}
                        granularity={period}
                        isValidRange={isValidRange}
                        placeholder={t('events.time_range_placeholder')}
                        dateOnly
                        showClearButton={false}
                        expandToViewport
                    />

                    <SegmentedControl
                        selectedId={period}
                        onChange={({ detail }) => setPeriod(detail.selectedId as TMeteringPeriod)}
                        options={[
                            { text: t('models.metering.day'), id: 'day' },
                            { text: t('models.metering.month'), id: 'month' },
                        ]}
                    />
                </div>
            }
        />
    );
};
