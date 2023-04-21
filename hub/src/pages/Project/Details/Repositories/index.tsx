import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Button, Cards, Header, ListEmptyMessage, NavigateLink, Pagination, SpaceBetween, TextFilter } from 'components';

import { useBreadcrumbs, useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useGetProjectReposQuery } from 'services/project';

export const ProjectRepositories: React.FC = () => {
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
        {
            text: t('projects.repositories'),
            href: ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName),
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
                        href={ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(paramProjectName, repo.repo_info.repo_name)}
                    >
                        {repo.repo_info.repo_name}
                    </NavigateLink>
                ),

                sections: [
                    {
                        id: 'owner',
                        header: t('projects.repo.card.owner'),
                        content: (repo) => repo.repo_info.repo_user_name,
                    },
                    {
                        id: 'last_run',
                        header: t('projects.repo.card.last_run'),
                        content: (repo) => repo.last_run_at,
                    },
                    {
                        id: 'tags_count',
                        header: t('projects.repo.card.tags_count'),
                        content: (repo) => repo.tags_count,
                    },
                ],
            }}
            items={items}
            loading={isLoading}
            loadingText="Loading"
            selectionType="multi"
            header={
                <Header
                    counter={renderCounter()}
                    actions={
                        <SpaceBetween size="xs" direction="horizontal">
                            <Button disabled>{t('common.delete')}</Button>
                        </SpaceBetween>
                    }
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
