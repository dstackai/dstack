import React from 'react';
import { useTranslation } from 'react-i18next';
import { usePresetViewer } from 'PublicApp/PresetApp';

import { Alert, Button, ButtonWithConfirmation, Header, Loader, PropertyFilter, SpaceBetween, Table, Tabs } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useAppSelector, useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { PresetListQueryArgs, useLazyGetAllPresetsQuery } from 'services/preset';

import { selectAuthToken } from 'App/slice';

import { useColumnsDefinitions, useFilters, usePresetsDelete, usePresetsTableEmptyMessages } from './hooks';

export const PresetList: React.FC = () => {
    const { t } = useTranslation();
    const { isAuthenticated, scope, setScope } = usePresetViewer();
    const authToken = useAppSelector(selectAuthToken);

    return (
        <PresetListTable
            key={`${authToken ?? ''}:${isAuthenticated}:${scope}`}
            authToken={authToken}
            scope={scope}
            isAuthenticated={isAuthenticated}
            tabs={
                isAuthenticated && (
                    <Tabs
                        activeTabId={scope}
                        tabs={[
                            { id: 'mine', label: t('presets.my_projects') },
                            { id: 'public', label: t('presets.public') },
                        ]}
                        onChange={({ detail }) => setScope(detail.activeTabId as 'mine' | 'public')}
                    />
                )
            }
        />
    );
};

const PresetListTable: React.FC<{
    authToken?: string;
    scope: 'public' | 'mine';
    isAuthenticated: boolean;
    tabs?: React.ReactNode;
}> = ({ authToken, scope, isAuthenticated, tabs }) => {
    const { t } = useTranslation();
    const isPublic = scope === 'public';

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
    } = useFilters({ scope });

    const { isDeleting, deletePresets } = usePresetsDelete();

    const { renderEmptyMessage, renderNoMatchMessage } = usePresetsTableEmptyMessages({
        clearFilter,
        isDisabledClearFilter,
        isPublic,
    });

    const { data, error, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IPreset, PresetListQueryArgs>({
        useLazyQuery: useLazyGetAllPresetsQuery,
        args: { ...filteringRequestParams, scope, authToken, limit: DEFAULT_TABLE_PAGE_SIZE } as PresetListQueryArgs,

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

    const { columns } = useColumnsDefinitions({ isPublic });
    const loadError = error ? (
        <Alert type="error" header={t('presets.load_error_title')}>
            {t('presets.load_error_message')}
        </Alert>
    ) : undefined;

    const { items, actions, collectionProps } = useCollection<IPreset>(data ?? [], {
        filtering: {
            empty: loadError ?? renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        selection: {},
    });

    const { selectedItems } = collectionProps;
    const canDelete = isAuthenticated && data.some((preset) => preset.can_delete);
    const canDeleteSelected = canDelete && !!selectedItems?.length && selectedItems.every((preset) => preset.can_delete);

    const deleteSelected = () => {
        if (!canDeleteSelected || !selectedItems?.length) return;

        deletePresets([...selectedItems]).then(() => {
            actions.setSelectedItems([]);
            refreshList();
        });
    };

    const isDisabledDelete = isDeleting || !canDeleteSelected;

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            selectionType={canDelete ? 'multi' : undefined}
            isItemDisabled={(preset) => !preset.can_delete}
            stickyHeader={true}
            header={
                <SpaceBetween size="l">
                    <Header
                        variant="awsui-h1-sticky"
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
                                {canDelete && (
                                    <ButtonWithConfirmation
                                        disabled={isDisabledDelete}
                                        formAction="none"
                                        onClick={deleteSelected}
                                        confirmTitle={t('presets.delete_confirm_title')}
                                        confirmContent={t('presets.delete_confirm_message')}
                                    >
                                        {t('common.delete')}
                                    </ButtonWithConfirmation>
                                )}

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
                    {tabs}
                </SpaceBetween>
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
            footer={
                <SpaceBetween size="m">
                    {data.length > 0 && loadError}
                    <Loader show={isLoadingMore} padding={{ vertical: 'm' }} />
                </SpaceBetween>
            }
        />
    );
};
