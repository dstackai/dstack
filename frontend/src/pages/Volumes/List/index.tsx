import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ButtonWithConfirmation, Header, Loader, PropertyFilter, SpaceBetween, Table, Toggle } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetAllVolumesQuery } from 'services/volume';

import { useColumnsDefinitions, useFilters, useVolumesDelete, useVolumesTableEmptyMessages } from './hooks';

import styles from './styles.module.scss';

export const VolumeList: React.FC = () => {
    const { t } = useTranslation();
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

    const { isDeleting, deleteVolumes } = useVolumesDelete();

    const { renderEmptyMessage, renderNoMatchMessage } = useVolumesTableEmptyMessages({
        clearFilter,
        isDisabledClearFilter,
    });

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IVolume, TVolumesListRequestParams>({
        useLazyQuery: useLazyGetAllVolumesQuery,
        args: { ...filteringRequestParams, limit: DEFAULT_TABLE_PAGE_SIZE },

        getPaginationParams: (lastFleet) => ({
            prev_created_at: lastFleet.created_at,
            prev_id: lastFleet.id,
        }),
    });

    const { columns } = useColumnsDefinitions();

    useBreadcrumbs([
        {
            text: t('volume.volumes'),
            href: ROUTES.VOLUMES.LIST,
        },
    ]);

    const { items, collectionProps, actions } = useCollection(data, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const deleteSelectedVolumes = () => {
        if (!selectedItems?.length) return;

        deleteVolumes([...selectedItems])
            .finally(() => {
                refreshList();
                actions.setSelectedItems([]);
            })
            .catch(console.log);
    };

    const isDisabledDeleteSelected = !selectedItems?.length || isDeleting;

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            stickyHeader={true}
            header={
                <Header
                    variant="awsui-h1-sticky"
                    actions={
                        <SpaceBetween size="xs" direction="horizontal">
                            <ButtonWithConfirmation
                                disabled={isDisabledDeleteSelected}
                                formAction="none"
                                onClick={deleteSelectedVolumes}
                                confirmTitle={t('volume.delete_volumes_confirm_title')}
                                confirmContent={t('volume.delete_volumes_confirm_message')}
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
                    {t('volume.volumes')}
                </Header>
            }
            selectionType="multi"
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
                            {t('volume.active_only')}
                        </Toggle>
                    </div>
                </div>
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
