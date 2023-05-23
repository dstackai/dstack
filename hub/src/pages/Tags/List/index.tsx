import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Button, Header, ListEmptyMessage, NavigateLink, Pagination, Table, TextFilter } from 'components';

import { useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useGetTagsQuery } from 'services/tag';

export const TagList: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramRepoId = params.repoId ?? '';

    const { data, isLoading } = useGetTagsQuery(
        {
            project_name: paramProjectName,
            repo_id: paramRepoId,
        },
        {
            pollingInterval: 10000,
        },
    );

    const COLUMN_DEFINITIONS = [
        {
            id: 'tag_name',
            header: t('projects.tag.tag_name'),
            cell: (item: ITag) => (
                <NavigateLink href={ROUTES.PROJECT.DETAILS.TAGS.DETAILS.FORMAT(paramProjectName, paramRepoId, item.tag_name)}>
                    {item.tag_name}
                </NavigateLink>
            ),
        },
        {
            id: 'run_name',
            header: t('projects.tag.run_name'),
            cell: (item: ITag) => item.run_name,
        },
        {
            id: 'run_name',
            header: t('projects.tag.artifacts'),
            cell: (item: ITag) => item.artifact_heads.length,
        },
    ];

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.tag.empty_message_title')} message={t('projects.tag.empty_message_text')} />
        );
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('common.nomatch_message_title')} message={t('common.nomatch_message_text')}>
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
            header={<Header>{t('projects.tag.list_page_title')}</Header>}
            filter={
                <TextFilter
                    {...filterProps}
                    filteringPlaceholder={t('projects.tag.search_placeholder')}
                    countText={t('common.match_count_with_value', { count: filteredItemsCount })}
                    disabled={isLoading}
                />
            }
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
        />
    );
};
