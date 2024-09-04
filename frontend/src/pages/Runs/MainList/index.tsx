import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { sortBy as _sortBy } from 'lodash';

import { Button, FormField, Header, Pagination, SelectCSD, SpaceBetween, Table, Toggle } from 'components';
import { useProjectDropdown } from 'layouts/AppLayout/hooks';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useCollection } from 'hooks';
import { useLazyGetRunsQuery } from 'services/run';

import { useAbortRuns, useColumnsDefinitions, useDeleteRuns, useDisabledStatesForButtons, useStopRuns } from '../List/hooks';
import { useEmptyMessages } from '../List/hooks/useEmptyMessages';
import { useFilters } from '../List/hooks/useFilters';
import { Preferences } from '../List/Preferences';
import { useRunListPreferences } from '../List/Preferences/useRunListPreferences';

import styles from '../List/styles.module.scss';

export const List: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const { selectedProject } = useProjectDropdown();
    const [preferences] = useRunListPreferences();
    const [data, setData] = useState<IRun[]>([]);
    const [pagesCount, setPagesCount] = useState<number>(1);
    const [disabledNext, setDisabledNext] = useState(false);

    const { selectedRepo, setSelectedRepo, repoOptions, clearSelected, onlyActive, setOnlyActive } = useFilters({
        repoSearchKey: 'repo',
        selectedProject: selectedProject ?? undefined,
        localStorePrefix: 'main-run-list-page',
    });

    const [getRuns, { isLoading, isFetching }] = useLazyGetRunsQuery();

    const isDisabledPagination = isLoading || isFetching || data.length === 0;

    const getRunsRequest = (params?: Partial<TRunsRequestParams>) => {
        return getRuns({
            project_name: selectedProject ?? undefined,
            repo_id: selectedRepo?.value,
            only_active: onlyActive,
            limit: DEFAULT_TABLE_PAGE_SIZE,
            ...params,
        }).unwrap();
    };

    useEffect(() => {
        getRunsRequest().then((result) => {
            setPagesCount(1);
            setDisabledNext(false);
            setData(result);
        });
    }, [selectedProject, selectedRepo?.value, onlyActive]);

    const isDisabledClearFilter = !selectedRepo && !onlyActive;

    const { stopRuns, isStopping } = useStopRuns();
    const { abortRuns, isAborting } = useAbortRuns();
    const { deleteRuns, isDeleting } = useDeleteRuns();

    const { columns } = useColumnsDefinitions();

    const nextPage = async () => {
        if (data.length === 0 || disabledNext) {
            return;
        }

        try {
            const result = await getRunsRequest({
                prev_submitted_at: data[data.length - 1].submitted_at,
                prev_run_id: data[data.length - 1].id,
            });

            if (result.length > 0) {
                setPagesCount((count) => count + 1);
                setData(result);
            } else {
                setDisabledNext(true);
            }
        } catch (e) {
            console.log(e);
        }
    };

    const prevPage = async () => {
        if (pagesCount === 1) {
            return;
        }

        try {
            const result = await getRunsRequest({
                prev_submitted_at: data[0].submitted_at,
                prev_run_id: data[0].id,
                ascending: true,
            });

            setDisabledNext(false);

            if (result.length > 0) {
                setPagesCount((count) => count - 1);
                setData(result);
            } else {
                setPagesCount(1);
            }
        } catch (e) {
            console.log(e);
        }
    };

    const clearFilter = () => {
        actions.setFiltering('');
        clearSelected();
        setSearchParams({});
    };

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        isDisabledClearFilter,
        clearFilter,
    });

    const sortedData = useMemo(() => {
        if (!data) return [];

        return _sortBy(data, [(i) => -i.submitted_at]);
    }, [data]);

    const { items, actions, collectionProps } = useCollection(sortedData ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        selection: {},
        pagination: { pageSize: 20 },
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
            loading={isLoading || isFetching}
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

                            <Button formAction="none" onClick={deleteClickHandle} disabled={isDisabledDeleteButton}>
                                {t('common.delete')}
                            </Button>
                        </SpaceBetween>
                    }
                >
                    {t('projects.runs')}
                </Header>
            }
            filter={
                <div className={styles.selectFilters}>
                    <div className={styles.select}>
                        <FormField label={t('projects.run.repo')}>
                            <SelectCSD
                                disabled={!repoOptions?.length}
                                options={repoOptions}
                                selectedOption={selectedRepo}
                                onChange={(event) => {
                                    setSelectedRepo(event.detail.selectedOption);
                                }}
                                placeholder={t('projects.run.repo_placeholder')}
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
            pagination={
                <Pagination
                    currentPageIndex={pagesCount}
                    pagesCount={pagesCount}
                    openEnd={!disabledNext}
                    disabled={isDisabledPagination}
                    onPreviousPageClick={prevPage}
                    onNextPageClick={nextPage}
                />
            }
        />
    );
};
