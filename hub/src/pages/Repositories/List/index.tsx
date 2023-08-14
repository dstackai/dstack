import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { format } from 'date-fns';

import { Button, Cards, ConfirmationDialog, Header, ListEmptyMessage, NavigateLink, Pagination, TextFilter } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs, useCollection, useNotifications } from 'hooks';
import { getRepoDisplayName } from 'libs/repo';
import { ROUTES } from 'routes';
import { useDeleteProjectRepoMutation, useGetProjectReposQuery } from 'services/project';

export const RepositoryList: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const [pushNotification] = useNotifications();

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const { data, isLoading } = useGetProjectReposQuery({ name: paramProjectName });

    const [deleteRepos, { isLoading: isDeletingRepos }] = useDeleteProjectRepoMutation();

    const sortingData = useMemo(() => {
        if (!data) return [];

        return [...data].sort((a, b) => b.last_run_at - a.last_run_at);
    }, [data]);

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

    const { items, actions, filteredItemsCount, collectionProps, filterProps, paginationProps } = useCollection(sortingData, {
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

    const deleteSelectedReposHandler = () => {
        const { selectedItems } = collectionProps;

        if (selectedItems?.length) {
            deleteRepos({
                name: paramProjectName,
                repo_ids: selectedItems.map((repo) => repo.repo_id),
            })
                .unwrap()
                .then(() => actions.setSelectedItems([]))
                .catch((error) => {
                    pushNotification({
                        type: 'error',
                        content: t('common.server_error', { error: error?.error }),
                    });
                });
        }
        setShowConfirmDelete(false);
    };

    const renderCounter = () => {
        const { selectedItems } = collectionProps;

        if (!sortingData.length) return '';

        if (selectedItems?.length) return `(${selectedItems?.length}/${data?.length ?? 0})`;

        return `(${sortingData.length})`;
    };

    const getDisableDeleteButton = () => {
        const { selectedItems } = collectionProps;

        return isDeletingRepos || !selectedItems?.length;
    };

    return (
        <>
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
                        actions={
                            <Button disabled={getDisableDeleteButton()} onClick={toggleDeleteConfirm}>
                                {t('common.delete')}
                            </Button>
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

            <ConfirmationDialog
                visible={showDeleteConfirm}
                onDiscard={toggleDeleteConfirm}
                onConfirm={deleteSelectedReposHandler}
            />
        </>
    );
};
