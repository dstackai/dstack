import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { format } from 'date-fns';

import {
    Button,
    Header,
    ListEmptyMessage,
    NavigateLink,
    Pagination,
    SpaceBetween,
    StatusIndicator,
    Table,
    TextFilter,
} from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useCollection, useNotifications } from 'hooks';
import { getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';
import { useDeleteRunsMutation, useGetRunsQuery, useStopRunsMutation } from 'services/run';

import { isAvailableAbortingForRun, isAvailableDeletingForRun, isAvailableStoppingForRun } from '../utils';

export const RunList: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramRepoId = params.repoId ?? '';
    const [pushNotification] = useNotifications();

    const { data, isLoading } = useGetRunsQuery(
        {
            name: paramProjectName,
            repo_id: paramRepoId,
        },
        {
            pollingInterval: 10000,
        },
    );

    const [stopRun, { isLoading: isStopping }] = useStopRunsMutation();
    const [deleteRun, { isLoading: isDeleting }] = useDeleteRunsMutation();

    const COLUMN_DEFINITIONS = [
        {
            id: 'run_name',
            header: t('projects.run.run_name'),
            cell: (item: IRun) => (
                <NavigateLink href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRepoId, item.run_name)}>
                    {item.run_name}
                </NavigateLink>
            ),
        },
        {
            id: 'workflow_name',
            header: `${t('projects.run.workflow_name')}`,
            cell: (item: IRun) => item.workflow_name ?? item.provider_name,
        },
        {
            id: 'hub_user_name',
            header: `${t('projects.run.hub_user_name')}`,
            cell: (item: IRun) => item.hub_user_name,
        },
        {
            id: 'status',
            header: t('projects.run.status'),
            cell: (item: IRun) => (
                <StatusIndicator type={getStatusIconType(item.status)}>
                    {t(`projects.run.statuses.${item.status}`)}
                </StatusIndicator>
            ),
        },
        {
            id: 'submitted_at',
            header: t('projects.run.submitted_at'),
            cell: (item: IRun) => format(new Date(item.submitted_at), DATE_TIME_FORMAT),
        },
        {
            id: 'artifacts',
            header: t('projects.run.artifacts_count'),
            cell: (item: IRun) => item.artifact_heads?.length ?? '-',
        },
    ];
    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.run.empty_message_title')} message={t('projects.run.empty_message_text')} />
        );
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.run.nomatch_message_title')} message={t('projects.run.nomatch_message_text')}>
                <Button onClick={onClearFilter}>{t('common.clearFilter')}</Button>
            </ListEmptyMessage>
        );
    };

    const { items, actions, filteredItemsCount, collectionProps, filterProps, paginationProps } = useCollection(data ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(() => actions.setFiltering('')),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const abortClickHandle = () => {
        if (!selectedItems?.length) return;

        stopRun({
            name: paramProjectName,
            repo_id: paramRepoId,
            run_names: selectedItems.map((item) => item.run_name),
            abort: true,
        })
            .unwrap()
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

        stopRun({
            name: paramProjectName,
            repo_id: paramRepoId,
            run_names: selectedItems.map((item) => item.run_name),
            abort: false,
        })
            .unwrap()
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

        deleteRun({
            name: paramProjectName,
            repo_id: paramRepoId,
            run_names: selectedItems.map((item) => item.run_name),
        })
            .unwrap()
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });
    };

    const isDisabledAbortButton = useMemo<boolean>(() => {
        return (
            !selectedItems?.length || selectedItems.some((item) => !isAvailableAbortingForRun(item)) || isStopping || isDeleting
        );
    }, [selectedItems, isStopping, isDeleting]);

    const isDisabledStopButton = useMemo<boolean>(() => {
        return (
            !selectedItems?.length || selectedItems.some((item) => !isAvailableStoppingForRun(item)) || isStopping || isDeleting
        );
    }, [selectedItems, isStopping, isDeleting]);

    const isDisabledDeleteButton = useMemo<boolean>(() => {
        return (
            !selectedItems?.length || selectedItems.some((item) => !isAvailableDeletingForRun(item)) || isStopping || isDeleting
        );
    }, [selectedItems, isStopping, isDeleting]);

    return (
        <Table
            {...collectionProps}
            columnDefinitions={COLUMN_DEFINITIONS}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            selectionType="multi"
            stickyHeader={true}
            header={
                <Header
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
                <TextFilter
                    {...filterProps}
                    filteringPlaceholder={t('projects.run.search_placeholder')}
                    countText={t('common.match_count_with_value', { count: filteredItemsCount })}
                    disabled={isLoading}
                />
            }
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
        />
    );
};
