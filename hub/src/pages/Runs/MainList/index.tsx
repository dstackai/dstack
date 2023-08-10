import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { /*get as _get,*/ sortBy as _sortBy, uniqBy as _uniqBy } from 'lodash';

import {
    Button,
    FormField,
    Header,
    ListEmptyMessage,
    Pagination,
    SelectCSD,
    SelectCSDProps,
    SpaceBetween,
    Table,
    // TextFilter,
    Toggle,
} from 'components';

import { useCollection } from 'hooks';
import { useGetAllRunsQuery } from 'services/run';

import { unfinishedRuns } from '../constants';
import { useAbortRuns, useColumnsDefinitions, useDeleteRuns, useDisabledStatesForButtons, useStopRuns } from '../List/hooks';

import styles from './styles.module.scss';

// export const SEARCHABLE_COLUMNS = [
//     'run_head.run_name',
//     'run_head.job_heads.[0].configuration_path',
//     'run_head.job_heads.[0].instance_type',
//     'run_head.hub_user_name',
//     'run_head.status',
// ];

export const List: React.FC = () => {
    const { t } = useTranslation();
    const [selectedProject, setSelectedProject] = useState<SelectCSDProps.Option | null>(null);
    const [selectedRepo, setSelectedRepo] = useState<SelectCSDProps.Option | null>(null);
    const [onlyActive, setOnlyActive] = useState<boolean>(false);

    const isFirstRunsFetchRef = useRef(true);

    const { data, isLoading } = useGetAllRunsQuery(undefined, {
        pollingInterval: 10000,
    });

    const { stopRuns, isStopping } = useStopRuns();
    const { abortRuns, isAborting } = useAbortRuns();
    const { deleteRuns, isDeleting } = useDeleteRuns();

    const { columns } = useColumnsDefinitions();

    useEffect(() => {
        if (data && isFirstRunsFetchRef.current) {
            isFirstRunsFetchRef.current = false;
            const hasUnfinished = data.some((run) => unfinishedRuns.includes(run.run_head.status));
            setOnlyActive(hasUnfinished);
        }
    }, [data]);

    const clearFilter = () => {
        actions.setFiltering('');
        setSelectedProject(null);
        setSelectedRepo(null);
        setOnlyActive(false);
    };
    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.run.empty_message_title')} message={t('projects.run.empty_message_text')} />
        );
    };

    const renderNoMatchMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.run.nomatch_message_title')} message={t('projects.run.nomatch_message_text')}>
                <Button onClick={clearFilter}>{t('common.clearFilter')}</Button>
            </ListEmptyMessage>
        );
    };

    const sortedData = useMemo(() => {
        if (!data) return [];

        return _sortBy(data, [(i) => -i.run_head.submitted_at]);
    }, [data]);

    const { items, actions, /*filteredItemsCount,*/ collectionProps, filterProps, paginationProps } = useCollection(
        sortedData ?? [],
        {
            filtering: {
                empty: renderEmptyMessage(),
                noMatch: renderNoMatchMessage(),

                filteringFunction: (runItem /*, filteringText*/) => {
                    // const filteringTextLowerCase = filteringText.toLowerCase();

                    if (selectedProject?.value && runItem.project !== selectedProject.value) return false;

                    if (selectedRepo?.value && runItem.repo_id !== selectedRepo.value) return false;

                    if (onlyActive && !unfinishedRuns.includes(runItem.run_head.status)) return false;

                    // return SEARCHABLE_COLUMNS.map((key) => _get(runItem, key)).some(
                    //     (value) => typeof value === 'string' && value.toLowerCase().indexOf(filteringTextLowerCase) > -1,
                    // );

                    return true;
                },
            },
            pagination: { pageSize: 20 },
            selection: {},
        },
    );

    const { selectedItems } = collectionProps;

    const { isDisabledAbortButton, isDisabledStopButton, isDisabledDeleteButton } = useDisabledStatesForButtons({
        selectedRuns: selectedItems,
        isStopping,
        isAborting,
        isDeleting,
    });

    const projectOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!data?.length) return [];

        return _uniqBy(
            data.map((run) => ({ label: run.project, value: run.project })),
            (option) => option.value,
        );
    }, [data]);

    const repoOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!data?.length) return [];

        return _uniqBy(
            data.map((run) => ({ label: run.repo?.repo_info.repo_name ?? 'No repo', value: run.repo?.repo_id ?? '-' })),
            (option) => option.value,
        );
    }, [data]);

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

    const isDisabledClearFilter = !selectedProject && !selectedRepo && !filterProps.filteringText && !onlyActive;

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
                <div>
                    {/*<TextFilter*/}
                    {/*    {...filterProps}*/}
                    {/*    filteringPlaceholder={t('projects.run.search_placeholder')}*/}
                    {/*    countText={t('common.match_count_with_value', { count: filteredItemsCount })}*/}
                    {/*    disabled={isLoading}*/}
                    {/*/>*/}
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
                                    expandToViewport={true}
                                    placeholder={t('projects.run.project_placeholder')}
                                />
                            </FormField>
                        </div>

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
                </div>
            }
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
        />
    );
};
