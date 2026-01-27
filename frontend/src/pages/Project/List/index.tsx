import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button, ButtonWithConfirmation, Header, ListEmptyMessage, Loader, SpaceBetween, Table, TextFilter } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetProjectsQuery } from 'services/project';

import { useCheckAvailableProjectPermission } from '../hooks/useCheckAvailableProjectPermission';
import { useDeleteProject } from '../hooks/useDeleteProject';
import { useColumnsDefinitions } from './hooks';

export const ProjectList: React.FC = () => {
    const { t } = useTranslation();

    const { isAvailableDeletingPermission, isAvailableProjectManaging } = useCheckAvailableProjectPermission();
    const { deleteProject, deleteProjects, isDeleting } = useDeleteProject();
    const [filteringText, setFilteringText] = useState('');
    const [namePattern, setNamePattern] = useState<string>('');
    const navigate = useNavigate();

    const { data, isLoading, refreshList, isLoadingMore, totalCount } = useInfiniteScroll<IProject, TGetProjectListParams>({
        useLazyQuery: useLazyGetProjectsQuery,
        args: { name_pattern: namePattern, limit: DEFAULT_TABLE_PAGE_SIZE },

        getPaginationParams: (lastProject) => ({
            prev_created_at: lastProject.created_at,
            prev_id: lastProject.project_id,
        }),
    });

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
            href: ROUTES.PROJECT.LIST,
        },
    ]);

    const addProjectHandler = () => {
        navigate(ROUTES.PROJECT.ADD);
    };

    const onClearFilter = () => {
        setNamePattern('');
        setFilteringText('');
    };

    const renderEmptyMessage = (): React.ReactNode => {
        if (isLoading) {
            return null;
        }

        if (filteringText) {
            return (
                <ListEmptyMessage title={t('projects.nomatch_message_title')} message={t('projects.nomatch_message_text')}>
                    <Button onClick={onClearFilter}>{t('projects.nomatch_message_button_label')}</Button>
                </ListEmptyMessage>
            );
        }

        return (
            <ListEmptyMessage title={t('projects.empty_message_title')} message={t('projects.empty_message_text')}>
                {isAvailableProjectManaging && <Button onClick={addProjectHandler}>{t('common.create')}</Button>}
            </ListEmptyMessage>
        );
    };

    const { items, collectionProps } = useCollection(data, {
        filtering: {
            empty: renderEmptyMessage(),
        },
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
        if (typeof totalCount !== 'number') return '';

        return `(${totalCount})`;
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

                                    <Button onClick={addProjectHandler}>{t('common.create')}</Button>

                                    <Button
                                        iconName="refresh"
                                        disabled={isLoading}
                                        ariaLabel={t('common.refresh')}
                                        onClick={refreshList}
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
                        filteringText={filteringText}
                        onChange={({ detail }) => setFilteringText(detail.filteringText)}
                        onDelayedChange={() => setNamePattern(filteringText)}
                        disabled={isLoading}
                        filteringPlaceholder={t('projects.search_placeholder') || ''}
                    />
                }
                footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
            />
        </>
    );
};
