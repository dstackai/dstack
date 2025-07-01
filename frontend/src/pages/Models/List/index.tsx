import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Header, Loader, PropertyFilter, Table } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetModelsQuery } from 'services/run';

import { useModelListPreferences } from './Preferences/useModelListPreferences';
import { useColumnsDefinitions, useEmptyMessages, useFilters } from './hooks';
import { Preferences } from './Preferences';

import { IModelExtended } from './types';

import styles from './styles.module.scss';

export const List: React.FC = () => {
    const { t } = useTranslation();

    const {
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        filteringRequestParams,
    } = useFilters();

    useBreadcrumbs([
        {
            text: t('navigation.models'),
            href: ROUTES.PROJECT.LIST,
        },
    ]);

    const { columns } = useColumnsDefinitions();
    const [preferences] = useModelListPreferences();

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IModelExtended, TRunsRequestParams>({
        useLazyQuery: useLazyGetModelsQuery,
        args: { ...filteringRequestParams, limit: DEFAULT_TABLE_PAGE_SIZE },

        getPaginationParams: (lastModel) => ({ prev_submitted_at: lastModel.submitted_at }),
    });

    const isDisabledClearFilter = !propertyFilterQuery.tokens.length;

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        clearFilter,
        isDisabledClearFilter,
    });

    const { items, collectionProps } = useCollection<IModelExtended>(data, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
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
            columnDisplay={preferences.contentDisplay}
            header={
                <Header
                    variant="awsui-h1-sticky"
                    actions={
                        <Button
                            iconName="refresh"
                            disabled={isLoading || isLoadingMore}
                            ariaLabel={t('common.refresh')}
                            onClick={refreshList}
                        />
                    }
                >
                    {t('navigation.models')}
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
            preferences={<Preferences />}
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
