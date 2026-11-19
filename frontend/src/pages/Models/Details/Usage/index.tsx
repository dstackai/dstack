import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useOutletContext } from 'react-router-dom';

import type { TableProps } from 'components';
import {
    Alert,
    Box,
    ColumnLayout,
    Container,
    DateRangePicker,
    Header,
    ListEmptyMessage,
    PropertyFilter,
    SegmentedControl,
    SpaceBetween,
    Table,
} from 'components';

import { useCollection } from 'hooks';
import { getServerError } from 'libs';
import { useGetMeteringQuery } from 'services/metering';

import {
    compareUsagePeriods,
    formatUsagePeriod,
    getUsageRequestParams,
    getUsageTotal,
    getUserOptionsRequestParams,
    relativeOptions,
    TUsagePeriod,
} from './helpers';
import { useFilteringOptions, useFilters, useTimeRange, useUserFilteringOptions } from './hooks';

import { IModelExtended } from '../../List/types';

import styles from './styles.module.scss';

// The token counts of a row and of the total
const TOKENS = ['input_tokens', 'cached_input_tokens', 'output_tokens'] as const;

export const ModelUsage: React.FC = () => {
    const { t } = useTranslation();
    const model = useOutletContext<IModelExtended>();
    const [period, setPeriod] = useState<TUsagePeriod>('month');
    const { timeRange, onChangeTimeRange, isValidRange } = useTimeRange();
    const { filteringRequestParams, propertyFilterQuery, onChangePropertyFilter, filteringProperties } = useFilters();

    const [requestParams, userOptionsRequestParams] = useMemo(() => {
        const request = { model, timeRange, period, filters: filteringRequestParams, now: new Date() };

        return [getUsageRequestParams(request), getUserOptionsRequestParams(request)];
    }, [model, timeRange, period, filteringRequestParams]);

    const { currentData, isFetching, error } = useGetMeteringQuery(requestParams);

    // A failed request shows its error, not the rows of an earlier answer
    const rows = useMemo(() => (error ? [] : (currentData ?? [])), [currentData, error]);
    const total = useMemo(() => getUsageTotal(rows), [rows]);

    const filteringOptions = useFilteringOptions(currentData);
    const { userFilteringOptions, filteringStatusType, handleLoadItems } = useUserFilteringOptions(userOptionsRequestParams);

    const columns: TableProps.ColumnDefinition<IMeteringRow>[] = [
        {
            id: 'period',
            header: t(`models.usage.${period}_utc`),
            cell: formatUsagePeriod,
            sortingComparator: compareUsagePeriods,
        },
        {
            id: 'project',
            header: t('models.project'),
            cell: (item) => item.project_name,
        },
        ...TOKENS.map((tokens) => ({
            id: tokens,
            header: t(`models.usage.${tokens}`),
            cell: (item: IMeteringRow) => item[tokens].toLocaleString(),
            sortingField: tokens,
        })),
    ];

    const { items, collectionProps } = useCollection<IMeteringRow>(rows, {
        filtering: {
            empty: error ? (
                <Alert type="error">{t('common.server_error', { error: getServerError(error) })}</Alert>
            ) : (
                <ListEmptyMessage
                    title={t('models.usage.empty_message_title')}
                    message={t('models.usage.empty_message_text')}
                />
            ),
        },
        sorting: {
            defaultState: { sortingColumn: columns[0], isDescending: true },
        },
    });

    return (
        <SpaceBetween size="l">
            <Table
                {...collectionProps}
                columnDefinitions={columns}
                items={items}
                loading={isFetching}
                loadingText={t('common.loading')}
                header={
                    <Header
                        actions={
                            <SegmentedControl
                                selectedId={period}
                                onChange={({ detail }) => setPeriod(detail.selectedId as TUsagePeriod)}
                                options={[
                                    { text: t('models.usage.day'), id: 'day' },
                                    { text: t('models.usage.month'), id: 'month' },
                                ]}
                            />
                        }
                    >
                        {t('models.usage.title')}
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
                                    enteredTextLabel: (value) => `Use: ${value}`,
                                }}
                                filteringOptions={[...filteringOptions, ...userFilteringOptions]}
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
                            dateOnly
                            showClearButton={false}
                            expandToViewport
                        />
                    </div>
                }
            />

            {/* The total of the rows. The API returns every row of a request, so the browser sums them */}
            {!!rows.length && (
                <Container header={<Header variant="h2">{t('models.usage.total')}</Header>}>
                    <ColumnLayout columns={4} variant="text-grid">
                        {TOKENS.map((tokens) => (
                            <div key={tokens}>
                                <Box variant="awsui-key-label">{t(`models.usage.${tokens}`)}</Box>
                                <Box fontSize="heading-xl" fontWeight="bold">
                                    {total[tokens].toLocaleString()}
                                </Box>
                            </div>
                        ))}
                    </ColumnLayout>
                </Container>
            )}
        </SpaceBetween>
    );
};
