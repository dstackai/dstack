import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Header, Loader, PropertyFilter, SpaceBetween, Table, Toggle } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetFleetsQuery } from 'services/fleet';

import { useColumnsDefinitions, useEmptyMessages, useFilters } from './hooks';
import { useDeleteFleet } from './useDeleteFleet';

import styles from './styles.module.scss';

export const FleetList: React.FC = () => {
    const { t } = useTranslation();

    useBreadcrumbs([
        {
            text: t('navigation.fleets'),
            href: ROUTES.FLEETS.LIST,
        },
    ]);

    const {
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        filteringRequestParams,
        onlyActive,
        onChangeOnlyActive,
        isDisabledClearFilter,
    } = useFilters();

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IFleet, TFleetListRequestParams>({
        useLazyQuery: useLazyGetFleetsQuery,
        args: { ...filteringRequestParams, limit: DEFAULT_TABLE_PAGE_SIZE },

        getPaginationParams: (lastFleet) => ({
            prev_created_at: lastFleet.created_at,
            prev_id: lastFleet.id,
        }),
    });

    const { columns } = useColumnsDefinitions();
    const { deleteFleets, isDeleting } = useDeleteFleet();
    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({ clearFilter, isDisabledClearFilter });

    const { items, collectionProps } = useCollection<IFleet>(data, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const isDisabledDeleteButton = !selectedItems?.length || isDeleting;

    const deleteClickHandle = () => {
        if (!selectedItems?.length) return;

        deleteFleets([...selectedItems]).catch(console.log);
    };

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
                            <Button formAction="none" onClick={deleteClickHandle} disabled={isDisabledDeleteButton}>
                                {t('common.delete')}
                            </Button>

                            <Button
                                iconName="refresh"
                                disabled={isLoading}
                                ariaLabel={t('common.refresh')}
                                onClick={refreshList}
                            />
                        </SpaceBetween>
                    }
                >
                    {t('navigation.fleets')}
                </Header>
            }
            filter={
                <div className={styles.filters}>
                    <div className={styles.propertyFilter}>
                        <PropertyFilter
                            query={propertyFilterQuery}
                            onChange={onChangePropertyFilter}
                            expandToViewport
                            hideOperations
                            i18nStrings={{
                                clearFiltersText: t('common.clearFilter'),
                                filteringAriaLabel: t('fleets.filter_property_placeholder'),
                                filteringPlaceholder: t('fleets.filter_property_placeholder'),
                                operationAndText: 'and',
                            }}
                            filteringOptions={filteringOptions}
                            filteringProperties={filteringProperties}
                        />
                    </div>

                    <div className={styles.activeOnly}>
                        <Toggle onChange={onChangeOnlyActive} checked={onlyActive}>
                            {t('fleets.active_only')}
                        </Toggle>
                    </div>
                </div>
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
