import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button, Header, Loader, PropertyFilter, SpaceBetween, Table, Toggle } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { useCheckingForFleetsInProjects } from 'hooks/useCheckingForFleetsInProjectsOfMember';
import { ROUTES } from 'routes';
import { useGetRunsQuery, useLazyGetRunsQuery } from 'services/run';

import { NoFleetProjectAlert } from 'pages/Project/components/NoFleetProjectAlert';

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
    const navigate = useNavigate();

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
        filteringStatusType,
        handleLoadItems,
    } = useFilters();
    const projectHavingFleetMap = useCheckingForFleetsInProjects({});

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

    const hasNoOtherFilters = Object.keys(filteringRequestParams).length <= 1;
    const isDisabledClearFilter = hasNoOtherFilters && !filteringRequestParams.only_active;
    const isOnlyActiveFilter = hasNoOtherFilters && !!filteringRequestParams.only_active;

    // "Active runs" is on by default, so an empty list under it alone doesn't say whether the user has any runs.
    const { data: anyRuns } = useGetRunsQuery(
        { limit: 1, only_active: false, job_submissions_limit: 0 },
        { skip: !isOnlyActiveFilter || isLoading || data.length > 0 },
    );

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        clearFilter,
        hasNoRuns: !data.length && (isDisabledClearFilter || (isOnlyActiveFilter && anyRuns?.length === 0)),
        isDisabledClearFilter,
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

    const launchHandle = () => {
        const projectName = filteringRequestParams.project_name;
        navigate(
            typeof projectName === 'string'
                ? `${ROUTES.RUNS.LAUNCH}?${new URLSearchParams({ project_name: projectName })}`
                : ROUTES.RUNS.LAUNCH,
        );
    };

    const projectDontHasFleet = Object.keys(projectHavingFleetMap).find((project) => !projectHavingFleetMap[project]);

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
                <>
                    <NoFleetProjectAlert
                        className={styles.noFleetAlert}
                        projectName={projectDontHasFleet ?? ''}
                        show={!!projectDontHasFleet}
                        dismissible={true}
                    />
                    <Header
                        variant="awsui-h1-sticky"
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
                                <Button variant="primary" onClick={launchHandle}>
                                    {t('runs.launch_button')}
                                </Button>

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
                </>
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
                            filteringOptions={filteringOptions}
                            filteringProperties={filteringProperties}
                            filteringStatusType={filteringStatusType}
                            onLoadItems={handleLoadItems}
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
