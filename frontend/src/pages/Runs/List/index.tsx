import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Header, Loader, PropertyFilter, SpaceBetween, Table, Toggle } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetRunsQuery } from 'services/run';

import { useRunListPreferences } from './Preferences/useRunListPreferences';
import {
    useAbortRuns,
    useColumnsDefinitions,
    useDeleteRuns,
    useDisabledStatesForButtons,
    useEmptyMessages,
    useFilters,
    useStopRuns,
} from './hooks';
import { Preferences } from './Preferences';

import styles from './styles.module.scss';

export const RunList: React.FC = () => {
    const { t } = useTranslation();
    const [preferences] = useRunListPreferences();

    useBreadcrumbs([
        {
            text: t('projects.runs'),
            href: ROUTES.RUNS.LIST,
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
    } = useFilters({
        localStorePrefix: 'administration-run-list-page',
    });

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IRun, TRunsRequestParams>({
        useLazyQuery: useLazyGetRunsQuery,
        args: { ...filteringRequestParams, limit: DEFAULT_TABLE_PAGE_SIZE, job_submissions_limit: 1 },
        getPaginationParams: (lastRun) => ({ prev_submitted_at: lastRun.submitted_at }),
    });

    const { stopRuns, isStopping } = useStopRuns();
    const { abortRuns, isAborting } = useAbortRuns();
    const {
        // deleteRuns,
        isDeleting,
    } = useDeleteRuns();

    const { columns } = useColumnsDefinitions();

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        clearFilter,
        noData: !data.length,
        isDisabledClearFilter: Object.keys(filteringRequestParams).length <= 1 && !filteringRequestParams.only_active,
    });

    const { items, actions, collectionProps } = useCollection(data ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const {
        isDisabledAbortButton,
        isDisabledStopButton,
        // isDisabledDeleteButton
    } = useDisabledStatesForButtons({
        selectedRuns: selectedItems,
        isStopping,
        isAborting,
        isDeleting,
    });

    const abortClickHandle = () => {
        if (!selectedItems?.length) return;

        abortRuns([...selectedItems]).then(() => actions.setSelectedItems([]));
    };

    const stopClickHandle = () => {
        if (!selectedItems?.length) return;

        stopRuns([...selectedItems]).then(() => actions.setSelectedItems([]));
    };

    // const deleteClickHandle = () => {
    //     if (!selectedItems?.length) return;
    //
    //     deleteRuns([...selectedItems]).catch(console.log);
    // };

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
            columnDisplay={preferences.contentDisplay}
            preferences={<Preferences />}
            header={
                <Header
                    variant="awsui-h1-sticky"
                    actions={
                        <SpaceBetween size="xs" direction="horizontal">
                            <Button formAction="none" onClick={abortClickHandle} disabled={isDisabledAbortButton}>
                                {t('common.abort')}
                            </Button>

                            <Button formAction="none" onClick={stopClickHandle} disabled={isDisabledStopButton}>
                                {t('common.stop')}
                            </Button>

                            {/*<Button formAction="none" onClick={deleteClickHandle} disabled={isDisabledDeleteButton}>*/}
                            {/*    {t('common.delete')}*/}
                            {/*</Button>*/}

                            <Button
                                iconName="refresh"
                                disabled={isLoading}
                                ariaLabel={t('common.refresh')}
                                onClick={refreshList}
                            />
                        </SpaceBetween>
                    }
                >
                    {t('projects.runs')}
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

                    <div className={styles.activeOnly}>
                        <Toggle onChange={onChangeOnlyActive} checked={onlyActive}>
                            {t('projects.run.active_only')}
                        </Toggle>
                    </div>
                </div>
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
