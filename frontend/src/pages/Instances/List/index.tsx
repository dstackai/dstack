import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Header, Loader, PropertyFilter, SpaceBetween, Table, Toggle } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useInfiniteScroll } from 'hooks';
import { useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetInstancesQuery } from 'services/instance';

import { useActions } from './hooks/useActions';
import { useColumnsDefinitions } from './hooks/useColumnDefinitions';
import { useEmptyMessages } from './hooks/useEmptyMessage';
import { useFilters } from './hooks/useFilters';

import styles from './styles.module.scss';

export const List: React.FC = () => {
    const { t } = useTranslation();

    useBreadcrumbs([
        {
            text: t('navigation.instances'),
            href: ROUTES.INSTANCES.LIST,
        },
    ]);

    const { columns } = useColumnsDefinitions();

    const {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        onlyActive,
        onChangeOnlyActive,
        isDisabledClearFilter,
    } = useFilters();

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IInstance, TInstanceListRequestParams>({
        useLazyQuery: useLazyGetInstancesQuery,
        args: { ...filteringRequestParams, limit: DEFAULT_TABLE_PAGE_SIZE },

        getPaginationParams: (lastInstance) => ({
            prev_created_at: lastInstance.created,
            prev_id: lastInstance.id,
        }),
    });

    const { deleteFleets, isDeleting } = useActions();

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({ clearFilter, isDisabledClearFilter });

    const { items, collectionProps } = useCollection<IInstance>(data, {
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
                    {t('navigation.instances')}
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
                                filteringAriaLabel: t('projects.run.filter_property_placeholder'),
                                filteringPlaceholder: t('projects.run.filter_property_placeholder'),
                                operationAndText: 'and',
                            }}
                            filteringOptions={filteringOptions}
                            filteringProperties={filteringProperties}
                        />
                    </div>

                    <div className={styles.activeOnly}>
                        <Toggle onChange={onChangeOnlyActive} checked={onlyActive}>
                            {t('fleets.instances.active_only')}
                        </Toggle>
                    </div>
                </div>
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
