import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { format } from 'date-fns';

import { Button, Header, ListEmptyMessage, NavigateLink, Pagination, SpaceBetween, Table, TextFilter } from 'components';

import { useBreadcrumbs } from 'hooks';
import { useCollection } from 'hooks';
import { getRepoDisplayName } from 'libs/repo';
import { ROUTES } from 'routes';
import { useGetProjectRepoQuery, useGetProjectRunsQuery } from 'services/project';

export const RepositoryDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramRepoId = params.repoId ?? '';

    const { data: repoData } = useGetProjectRepoQuery({
        name: paramProjectName,
        repo_id: paramRepoId,
    });

    useBreadcrumbs([
        {
            text: t('navigation.projects'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            text: t('projects.repositories'),
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            text: repoData ? getRepoDisplayName(repoData) : 'Loading...',
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(paramProjectName, paramRepoId),
        },
    ]);

    const COLUMN_DEFINITIONS = [
        {
            id: 'run_name',
            header: t('projects.run.run_name'),
            cell: (item: IRun) =>
                // TODO revert link after adding run details page
                // <NavigateLink href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRepoId, item.run_name)}>
                //     {item.run_name}
                // </NavigateLink>
                item.run_name,
        },
        {
            id: 'workflow_name',
            header: `${t('projects.run.workflow_name')}/${t('projects.run.provider_name')}`,
            cell: (item: IRun) => item.workflow_name ?? item.provider_name,
        },
        {
            id: 'status',
            header: t('projects.run.status'),
            cell: (item: IRun) => t(`projects.run.statuses.${item.status}`),
        },
        {
            id: 'submitted_at',
            header: t('projects.run.submitted_at'),
            cell: (item: IRun) => format(new Date(item.submitted_at), 'MM/dd/yyyy hh:mm'),
        },
        {
            id: 'artifacts',
            header: t('projects.run.artifacts'),
            cell: (item: IRun) => item.artifact_heads?.length ?? '-',
        },
    ];

    const { data, isLoading } = useGetProjectRunsQuery({
        name: paramProjectName,
        repo_id: paramRepoId,
    });

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
                            <Button formAction="none" disabled>
                                {t('common.stop')}
                            </Button>

                            <Button formAction="none" disabled>
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
