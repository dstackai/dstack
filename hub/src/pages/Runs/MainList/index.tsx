import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { /*get as _get,*/ sortBy as _sortBy, uniqBy as _uniqBy } from 'lodash';
import { format } from 'date-fns';

import {
    Button,
    FormField,
    Header,
    ListEmptyMessage,
    NavigateLink,
    Pagination,
    SelectCSD,
    SelectCSDProps,
    SpaceBetween,
    StatusIndicator,
    Table,
    // TextFilter,
    Toggle,
} from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useCollection, useNotifications } from 'hooks';
import { getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';
import { useDeleteRunsMutation, useGetAllRunsQuery, useStopRunsMutation } from 'services/run';

import { unfinishedRuns } from '../constants';
import { isAvailableAbortingForRun, isAvailableDeletingForRun, isAvailableStoppingForRun } from '../utils';

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
    const [pushNotification] = useNotifications();
    const [selectedProject, setSelectedProject] = useState<SelectCSDProps.Option | null>(null);
    const [selectedRepo, setSelectedRepo] = useState<SelectCSDProps.Option | null>(null);
    const [onlyActive, setOnlyActive] = useState<boolean>(false);

    const isFirstRunsFetchRef = useRef(true);

    const { data, isLoading } = useGetAllRunsQuery(undefined, {
        pollingInterval: 10000,
    });

    const [stopRun, { isLoading: isStopping }] = useStopRunsMutation();
    const [deleteRun, { isLoading: isDeleting }] = useDeleteRunsMutation();

    const COLUMN_DEFINITIONS = [
        {
            id: 'run_name',
            header: t('projects.run.run_name'),
            cell: (item: IRunListItem) => (
                <NavigateLink
                    href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(item.project, item.repo.repo_id, item.run_head.run_name)}
                >
                    {item.run_head.run_name}
                </NavigateLink>
            ),
        },
        {
            id: 'project',
            header: `${t('projects.run.project')}`,
            cell: (item: IRunListItem) => item.project,
        },
        {
            id: 'repo',
            header: `${t('projects.run.repo')}`,
            cell: (item: IRunListItem) => item.repo.repo_info.repo_name,
        },
        {
            id: 'configuration',
            header: `${t('projects.run.configuration')}`,
            cell: (item: IRunListItem) => item.run_head.job_heads?.[0].configuration_path,
        },
        {
            id: 'instance',
            header: `${t('projects.run.instance')}`,
            cell: (item: IRunListItem) => item.run_head.job_heads?.[0].instance_type,
        },
        {
            id: 'hub_user_name',
            header: `${t('projects.run.hub_user_name')}`,
            cell: (item: IRunListItem) => item.run_head.hub_user_name,
        },
        {
            id: 'status',
            header: t('projects.run.status'),
            cell: (item: IRunListItem) => (
                <StatusIndicator type={getStatusIconType(item.run_head.status)}>
                    {t(`projects.run.statuses.${item.run_head.status}`)}
                </StatusIndicator>
            ),
        },
        {
            id: 'submitted_at',
            header: t('projects.run.submitted_at'),
            cell: (item: IRunListItem) => format(new Date(item.run_head.submitted_at), DATE_TIME_FORMAT),
        },
        // {
        //     id: 'artifacts',
        //     header: t('projects.run.artifacts_count'),
        //     cell: (item: IRunListItem) => item.run_head.artifact_heads?.length ?? '-',
        // },
    ];

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

                    if (selectedRepo?.value && runItem.repo.repo_id !== selectedRepo.value) return false;

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
            data.map((run) => ({ label: run.repo.repo_info.repo_name, value: run.repo.repo_id })),
            (option) => option.value,
        );
    }, [data]);

    const abortClickHandle = () => {
        if (!selectedItems?.length) return;

        Promise.all(
            selectedItems.map((item) =>
                stopRun({
                    name: item.project,
                    repo_id: item.repo.repo_id,
                    run_names: [item.run_head.run_name],
                    abort: true,
                }).unwrap(),
            ),
        )
            .then(() => actions.setSelectedItems([]))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });
    };

    const stopClickHandle = () => {
        if (!selectedItems?.length) return;

        Promise.all(
            selectedItems.map((item) =>
                stopRun({
                    name: item.project,
                    repo_id: item.repo.repo_id,
                    run_names: [item.run_head.run_name],
                    abort: false,
                }).unwrap(),
            ),
        )
            .then(() => actions.setSelectedItems([]))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });
    };

    const deleteClickHandle = () => {
        if (!selectedItems?.length) return;

        Promise.all(
            selectedItems.map((item) =>
                deleteRun({
                    name: item.project,
                    repo_id: item.repo.repo_id,
                    run_names: [item.run_head.run_name],
                }).unwrap(),
            ),
        ).catch((error) => {
            pushNotification({
                type: 'error',
                content: t('common.server_error', { error: error?.error }),
            });
        });
    };

    const isDisabledAbortButton = useMemo<boolean>(() => {
        return (
            !selectedItems?.length ||
            selectedItems.some((item) => !isAvailableAbortingForRun(item.run_head.status)) ||
            isStopping ||
            isDeleting
        );
    }, [selectedItems, isStopping, isDeleting]);

    const isDisabledStopButton = useMemo<boolean>(() => {
        return (
            !selectedItems?.length ||
            selectedItems.some((item) => !isAvailableStoppingForRun(item.run_head.status)) ||
            isStopping ||
            isDeleting
        );
    }, [selectedItems, isStopping, isDeleting]);

    const isDisabledDeleteButton = useMemo<boolean>(() => {
        return (
            !selectedItems?.length ||
            selectedItems.some((item) => !isAvailableDeletingForRun(item.run_head.status)) ||
            isStopping ||
            isDeleting
        );
    }, [selectedItems, isStopping, isDeleting]);

    const isDisabledClearFilter = !selectedProject && !selectedRepo && !filterProps.filteringText && !onlyActive;

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            columnDefinitions={COLUMN_DEFINITIONS}
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
