import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Button, Header, ListEmptyMessage, NavigateLink, Pagination, SpaceBetween, Table, TextFilter } from 'components';

import { useBreadcrumbs } from 'hooks';
import { useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useGetProjectReposQuery, useGetProjectRunsQuery } from 'services/project';

export const RepositoryDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramRepoName = params.repoName ?? '';

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
            text: paramRepoName,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(paramProjectName, paramRepoName),
        },
    ]);

    const COLUMN_DEFINITIONS = [
        {
            id: 'run_name',
            header: t('projects.run.run_name'),
            cell: (item: IRun) => (
                <NavigateLink href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRepoName, item.run_name)}>
                    {item.run_name}
                </NavigateLink>
            ),
        },
        {
            id: 'workflow_name',
            header: t('projects.run.workflow_name'),
            cell: (item: IRun) => item.workflow_name,
        },
        {
            id: 'provider_name',
            header: t('projects.run.provider_name'),
            cell: (item: IRun) => item.provider_name,
        },
    ];

    const { data: repoListData, isLoading: reposIsLoading } = useGetProjectReposQuery({ name: paramProjectName });

    const repo: IRepo | undefined = repoListData?.find((repo) => repo.repo_info.repo_name === paramRepoName);

    const { data, isLoading: runsIsLoading } = useGetProjectRunsQuery(
        {
            name: paramProjectName,
            repo_id: repo?.repo_id,
        },
        { skip: !repoListData },
    );

    const isLoading = reposIsLoading || runsIsLoading;

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
