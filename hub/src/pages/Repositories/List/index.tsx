import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { format } from 'date-fns';

import { Button, Cards, Header, ListEmptyMessage, NavigateLink, Pagination, SpaceBetween, TextFilter } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs, useCollection } from 'hooks';
import { getRepoDisplayName } from 'libs/repo';
import { ROUTES } from 'routes';
import { useGetProjectReposQuery } from 'services/project';

export const RepositoryList: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';

    const { data, isLoading } = useGetProjectReposQuery({ name: paramProjectName });

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.repo.empty_message_title')} message={t('projects.repo.empty_message_text')} />
        );
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <ListEmptyMessage
                title={t('projects.repo.nomatch_message_title')}
                message={t('projects.repo.nomatch_message_text')}
            >
                <Button onClick={onClearFilter}>{t('projects.nomatch_message_button_label')}</Button>
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

    useBreadcrumbs([
        {
            text: t('navigation.projects'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
    ]);

    const renderCounter = () => {
        const { selectedItems } = collectionProps;

        if (!data?.length) return '';

        if (selectedItems?.length) return `(${selectedItems?.length}/${data?.length ?? 0})`;

        return `(${data.length})`;
    };

    return (
        <Cards
            {...collectionProps}
            cardDefinition={{
                header: (repo) => (
                    <NavigateLink
                        fontSize="heading-m"
                        href={ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(paramProjectName, repo.repo_id)}
                    >
                        {getRepoDisplayName(repo)}
                    </NavigateLink>
                ),

                sections: [
                    {
                        id: 'last_run',
                        header: t('projects.repo.card.last_run'),
                        content: (repo) => format(new Date(repo.last_run_at), DATE_TIME_FORMAT),
                    },
                    // {
                    //     id: 'tags_count',
                    //     header: t('projects.repo.card.tags_count'),
                    //     content: (repo) => repo.tags_count,
                    // },
                ],
            }}
            items={items}
            loading={isLoading}
            loadingText="Loading"
            selectionType="multi"
            stickyHeader={true}
            header={
                <Header
                    counter={renderCounter()}
                    // actions={
                    //     <SpaceBetween size="xs" direction="horizontal">
                    //         <Button disabled>{t('common.delete')}</Button>
                    //     </SpaceBetween>
                    // }
                >
                    {t('projects.repositories')}
                </Header>
            }
            filter={
                <TextFilter
                    {...filterProps}
                    filteringPlaceholder={t('projects.repo.search_placeholder') || ''}
                    countText={t('common.match_count_with_value', { count: filteredItemsCount }) ?? ''}
                    disabled={isLoading}
                />
            }
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
        />
    );
};
