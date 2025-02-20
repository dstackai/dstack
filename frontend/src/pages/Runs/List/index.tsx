import React from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { Button, FormField, Header, Loader, SelectCSD, SpaceBetween, Table, Toggle } from 'components';

import { useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';

import { useRunListPreferences } from './Preferences/useRunListPreferences';
import { DEFAULT_TABLE_PAGE_SIZE } from '../../../consts';
import { useLazyGetRunsQuery } from '../../../services/run';
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
    const [searchParams, setSearchParams] = useSearchParams();
    const [preferences] = useRunListPreferences();

    useBreadcrumbs([
        {
            text: t('projects.runs'),
            href: ROUTES.RUNS.LIST,
        },
    ]);

    const { projectOptions, selectedProject, setSelectedProject, onlyActive, setOnlyActive, clearSelected } = useFilters({
        projectSearchKey: 'project',
        localStorePrefix: 'administration-run-list-page',
    });

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IRun, TRunsRequestParams>({
        useLazyQuery: useLazyGetRunsQuery,
        args: { project_name: selectedProject?.value, only_active: onlyActive, limit: DEFAULT_TABLE_PAGE_SIZE },
        getPaginationParams: (lastRun) => ({ prev_submitted_at: lastRun.submitted_at }),
    });

    const isDisabledClearFilter = !selectedProject && !onlyActive;

    const { stopRuns, isStopping } = useStopRuns();
    const { abortRuns, isAborting } = useAbortRuns();
    const { deleteRuns, isDeleting } = useDeleteRuns();

    const { columns } = useColumnsDefinitions();

    const clearFilter = () => {
        clearSelected();
        setOnlyActive(false);
        setSearchParams({});
    };

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        isDisabledClearFilter,
        clearFilter,
    });

    const { items, actions, collectionProps } = useCollection(data ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const { isDisabledAbortButton, isDisabledStopButton, isDisabledDeleteButton } = useDisabledStatesForButtons({
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

    const deleteClickHandle = () => {
        if (!selectedItems?.length) return;

        deleteRuns([...selectedItems]).catch(console.log);
    };

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
                    <div className={styles.select}>
                        <FormField label={t('projects.run.project')}>
                            <SelectCSD
                                disabled={!projectOptions?.length}
                                options={projectOptions}
                                selectedOption={selectedProject}
                                onChange={(event) => {
                                    setSelectedProject(event.detail.selectedOption);
                                }}
                                placeholder={t('projects.run.project_placeholder')}
                                expandToViewport={true}
                                filteringType="auto"
                            />
                        </FormField>
                    </div>

                    <div className={styles.activeOnly}>
                        <Toggle onChange={({ detail }) => setOnlyActive(detail.checked)} checked={onlyActive}>
                            {t('projects.run.active_only')}
                        </Toggle>
                    </div>

                    <div className={styles.clear}>
                        <Button formAction="none" onClick={clearFilter} disabled={isDisabledClearFilter}>
                            {t('common.clearFilter')}
                        </Button>
                    </div>
                </div>
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
