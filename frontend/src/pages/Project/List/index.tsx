import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { get as _get } from 'lodash';

import {
    Button,
    ButtonWithConfirmation,
    Header,
    ListEmptyMessage,
    Pagination,
    SpaceBetween,
    Table,
    TextFilter,
} from 'components';

import { useBreadcrumbs, useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useGetProjectsQuery } from 'services/project';

import { useCheckAvailableProjectPermission } from '../hooks/useCheckAvailableProjectPermission';
import { useDeleteProject } from '../hooks/useDeleteProject';
import { useColumnsDefinitions } from './hooks';

const SEARCHABLE_COLUMNS = ['project_name', 'owner.username'];

export const ProjectList: React.FC = () => {
    const { t } = useTranslation();

    const { isLoading, isFetching, data, refetch } = useGetProjectsQuery();
    const { isAvailableDeletingPermission, isAvailableProjectManaging } = useCheckAvailableProjectPermission();
    const { deleteProject, deleteProjects, isDeleting } = useDeleteProject();
    const navigate = useNavigate();

    const sortedData = useMemo<IProject[]>(() => {
        if (!data) return [];

        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        return [...data].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    }, [data]);

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
            href: ROUTES.PROJECT.LIST,
        },
    ]);

    const addProjectHandler = () => {
        navigate(ROUTES.PROJECT.ADD);
    };

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.empty_message_title')} message={t('projects.empty_message_text')}>
                {isAvailableProjectManaging && <Button onClick={addProjectHandler}>{t('common.add')}</Button>}
            </ListEmptyMessage>
        );
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.nomatch_message_title')} message={t('projects.nomatch_message_text')}>
                <Button onClick={onClearFilter}>{t('projects.nomatch_message_button_label')}</Button>
            </ListEmptyMessage>
        );
    };

    const { items, actions, filteredItemsCount, collectionProps, filterProps, paginationProps } = useCollection(sortedData, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(() => actions.setFiltering('')),

            filteringFunction: (projectItem: IProject, filteringText) => {
                const filteringTextLowerCase = filteringText.toLowerCase();

                return SEARCHABLE_COLUMNS.map((key) => _get(projectItem, key)).some(
                    (value) => typeof value === 'string' && value.trim().toLowerCase().indexOf(filteringTextLowerCase) > -1,
                );
            },
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const deleteSelectedProjects = () => {
        if (!selectedItems?.length) return;

        deleteProjects([...selectedItems]).catch(console.log);
    };

    const isDisabledDeleteSelected = useMemo(() => {
        if (!selectedItems?.length || isDeleting) return true;

        return !selectedItems.every(isAvailableDeletingPermission);
    }, [selectedItems]);

    const { columns } = useColumnsDefinitions({
        loading: isLoading,
        onDeleteClick: isAvailableProjectManaging ? deleteProject : undefined,
    });

    const renderCounter = () => {
        if (!data?.length) return '';

        return `(${data.length})`;
    };

    return (
        <>
            <Table
                {...collectionProps}
                variant="full-page"
                columnDefinitions={columns}
                items={items}
                loading={isLoading || isFetching}
                loadingText={t('common.loading')}
                selectionType={isAvailableProjectManaging ? 'multi' : undefined}
                stickyHeader={true}
                header={
                    <Header
                        variant="awsui-h1-sticky"
                        counter={renderCounter()}
                        actions={
                            isAvailableProjectManaging && (
                                <SpaceBetween size="xs" direction="horizontal">
                                    <ButtonWithConfirmation
                                        disabled={isDisabledDeleteSelected}
                                        formAction="none"
                                        onClick={deleteSelectedProjects}
                                        confirmTitle={t('projects.edit.delete_projects_confirm_title')}
                                        confirmContent={t('projects.edit.delete_projects_confirm_message')}
                                    >
                                        {t('common.delete')}
                                    </ButtonWithConfirmation>

                                    <Button onClick={addProjectHandler}>{t('common.add')}</Button>

                                    <Button
                                        iconName="refresh"
                                        disabled={isLoading || isFetching}
                                        ariaLabel={t('common.refresh')}
                                        onClick={refetch}
                                    />
                                </SpaceBetween>
                            )
                        }
                    >
                        {t('projects.page_title')}
                    </Header>
                }
                filter={
                    <TextFilter
                        {...filterProps}
                        filteringPlaceholder={t('projects.search_placeholder') || ''}
                        countText={t('common.match_count_with_value', { count: filteredItemsCount }) ?? ''}
                        disabled={isLoading}
                    />
                }
                pagination={<Pagination {...paginationProps} disabled={isLoading} />}
            />
        </>
    );
};
