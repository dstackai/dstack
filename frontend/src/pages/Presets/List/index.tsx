import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ButtonWithConfirmation, Header, Loader, PropertyFilter, SpaceBetween, Table } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetAllPresetsQuery } from 'services/preset';

import { useColumnsDefinitions, useFilters, usePresetsDelete, usePresetsTableEmptyMessages } from './hooks';

export const PresetList: React.FC = () => {
    const { t } = useTranslation();

    const {
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        filteringRequestParams,
        isDisabledClearFilter,
        filteringStatusType,
        handleLoadItems,
    } = useFilters();

    const { isDeleting, deletePresets } = usePresetsDelete();

    const { renderEmptyMessage, renderNoMatchMessage } = usePresetsTableEmptyMessages({
        clearFilter,
        isDisabledClearFilter,
    });

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IPreset, TPresetsListRequestParams>({
        useLazyQuery: useLazyGetAllPresetsQuery,
        args: { ...filteringRequestParams, limit: DEFAULT_TABLE_PAGE_SIZE } as TPresetsListRequestParams,

        getPaginationParams: (lastPreset) => ({
            prev_created_at: lastPreset.created_at,
            prev_id: lastPreset.id,
        }),
    });

    useBreadcrumbs([
        {
            text: t('navigation.presets'),
            href: ROUTES.PRESETS.LIST,
        },
    ]);

    const { columns } = useColumnsDefinitions();

    const { items, actions, collectionProps } = useCollection<IPreset>(data ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const deleteSelected = () => {
        if (!selectedItems?.length) return;

        deletePresets([...selectedItems]).then(() => {
            actions.setSelectedItems([]);
            refreshList();
        });
    };

    const isDisabledDelete = isDeleting || !selectedItems?.length;

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            selectionType="multi"
            stickyHeader={true}
            header={
                <Header
                    variant="awsui-h1-sticky"
                    actions={
                        <SpaceBetween size="xs" direction="horizontal">
                            <ButtonWithConfirmation
                                disabled={isDisabledDelete}
                                formAction="none"
                                onClick={deleteSelected}
                                confirmTitle={t('presets.delete_confirm_title')}
                                confirmContent={t('presets.delete_confirm_message')}
                            >
                                {t('common.delete')}
                            </ButtonWithConfirmation>

                            <Button
                                iconName="refresh"
                                disabled={isLoading}
                                ariaLabel={t('common.refresh')}
                                onClick={refreshList}
                            />
                        </SpaceBetween>
                    }
                >
                    {t('presets.list_page_title')}
                </Header>
            }
            filter={
                <PropertyFilter
                    query={propertyFilterQuery}
                    onChange={onChangePropertyFilter}
                    expandToViewport
                    hideOperations
                    i18nStrings={{
                        clearFiltersText: t('common.clearFilter'),
                        filteringPlaceholder: t('presets.filter_property_placeholder'),
                    }}
                    filteringOptions={filteringOptions}
                    filteringProperties={filteringProperties}
                    filteringStatusType={filteringStatusType}
                    onLoadItems={handleLoadItems}
                />
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
