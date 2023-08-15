import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

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

export const ProjectList: React.FC = () => {
    const { t } = useTranslation();

    const { isLoading, data } = useGetProjectsQuery();
    const { isAvailableDeletingPermission } = useCheckAvailableProjectPermission();
    const { deleteProject, deleteProjects, isDeleting } = useDeleteProject();
    const navigate = useNavigate();

    useBreadcrumbs([
        {
            text: t('navigation.projects'),
            href: ROUTES.PROJECT.LIST,
        },
    ]);

    const addProjectHandler = () => {
        navigate(ROUTES.PROJECT.ADD);
    };

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.empty_message_title')} message={t('projects.empty_message_text')}>
                <Button onClick={addProjectHandler}>{t('common.add')}</Button>
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

    const { items, actions, filteredItemsCount, collectionProps, filterProps, paginationProps } = useCollection(data ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(() => actions.setFiltering('')),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const deleteSelectedProjects = () => {
        if (!selectedItems?.length) return;

        deleteProjects([...selectedItems]).catch(console.log);
    };

    const { columns } = useColumnsDefinitions({
        loading: isLoading || isDeleting,
        onDeleteClick: deleteProject,
    });

    const isDisabledDeleteSelected = useMemo(() => {
        if (!selectedItems?.length || isDeleting) return true;

        return !selectedItems.every(isAvailableDeletingPermission);
    }, [selectedItems]);

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
                loading={isLoading}
                loadingText={t('common.loading')}
                selectionType="multi"
                stickyHeader={true}
                header={
                    <Header
                        variant="awsui-h1-sticky"
                        counter={renderCounter()}
                        actions={
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
                            </SpaceBetween>
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
