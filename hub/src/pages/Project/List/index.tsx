import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import {
    Button,
    Cards,
    ConfirmationDialog,
    Header,
    ListEmptyMessage,
    NavigateLink,
    Pagination,
    SpaceBetween,
    TextFilter,
} from 'components';

import { useAppSelector, useBreadcrumbs, useCollection, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useDeleteProjectsMutation, useGetProjectsQuery } from 'services/project';

import { selectUserData } from 'App/slice';

import { getProjectRoleByUserName } from '../utils';

interface IProjectSettingsNodeProps {
    settingsKey: string;
    settingsValue: string;
}

export const ProjectSettingsNode: React.FC<IProjectSettingsNodeProps> = ({ settingsKey, settingsValue }) => {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <div>{settingsKey}:</div> {settingsValue}
        </div>
    );
};

export const ProjectList: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const userData = useAppSelector(selectUserData);
    const userName = userData?.user_name ?? '';
    const userGlobalRole = userData?.global_role ?? '';
    const { isLoading, data } = useGetProjectsQuery();
    const navigate = useNavigate();
    const [deleteProjects, { isLoading: isDeleting }] = useDeleteProjectsMutation();
    const [pushNotification] = useNotifications();

    useBreadcrumbs([
        {
            text: t('navigation.projects'),
            href: ROUTES.PROJECT.LIST,
        },
    ]);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

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

    const deleteSelectedProjectsHandler = () => {
        if (collectionProps.selectedItems?.length) {
            deleteProjects(collectionProps.selectedItems.map((project) => project.project_name))
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

    const editSelectedProjectHandler = () => {
        if (collectionProps.selectedItems?.length === 1)
            navigate(ROUTES.PROJECT.EDIT_BACKEND.FORMAT(collectionProps.selectedItems[0].project_name));
    };

    const renderCounter = () => {
        const { selectedItems } = collectionProps;

        if (!data?.length) return '';

        if (selectedItems?.length) return `(${selectedItems?.length}/${data?.length ?? 0})`;

        return `(${data.length})`;
    };

    const getIsTableItemDisabled = () => {
        return isDeleting;
    };

    const isDisabledEdit = useMemo(() => {
        if (collectionProps.selectedItems?.length !== 1) return true;

        return (
            collectionProps.selectedItems?.some(
                (item) => getProjectRoleByUserName(item, userName) !== 'admin' && userGlobalRole !== 'admin',
            ) ?? false
        );
    }, [isDeleting, userName, userGlobalRole, collectionProps.selectedItems]);

    const isDisabledDelete = useMemo(() => {
        if (isDeleting || collectionProps.selectedItems?.length === 0) return true;

        return (
            collectionProps.selectedItems?.some(
                (item) => getProjectRoleByUserName(item, userName) !== 'admin' && userGlobalRole !== 'admin',
            ) ?? false
        );
    }, [isDeleting, userName, userGlobalRole, collectionProps.selectedItems]);

    const getProjectSettings = (project: IProject) => {
        switch (project.backend.type) {
            case 'aws':
                return (
                    <div>
                        <ProjectSettingsNode
                            settingsKey="Region"
                            settingsValue={project.backend.region_name_title}
                        ></ProjectSettingsNode>
                        <ProjectSettingsNode
                            settingsKey="Bucket"
                            settingsValue={project.backend.s3_bucket_name}
                        ></ProjectSettingsNode>
                    </div>
                );
            case 'azure':
                return (
                    <div>
                        <ProjectSettingsNode
                            settingsKey="Location"
                            settingsValue={project.backend.location}
                        ></ProjectSettingsNode>
                        <ProjectSettingsNode
                            settingsKey="Storage account"
                            settingsValue={project.backend.storage_account}
                        ></ProjectSettingsNode>
                    </div>
                );
            case 'gcp':
                return (
                    <div>
                        <ProjectSettingsNode settingsKey="Region" settingsValue={project.backend.region}></ProjectSettingsNode>
                        <ProjectSettingsNode
                            settingsKey="Bucket"
                            settingsValue={project.backend.bucket_name}
                        ></ProjectSettingsNode>
                    </div>
                );
            case 'local':
                return '-';
        }
    };

    return (
        <>
            <Cards
                {...collectionProps}
                variant="full-page"
                cardDefinition={{
                    header: (project) => (
                        <NavigateLink
                            fontSize="heading-m"
                            href={ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(project.project_name)}
                        >
                            {project.project_name}
                        </NavigateLink>
                    ),

                    sections: [
                        {
                            id: 'type',
                            header: t('projects.card.backend'),
                            content: (project) => t(`projects.backend_type.${project.backend.type}`),
                        },
                        {
                            id: 'settings',
                            header: t('projects.card.settings'),
                            content: getProjectSettings,
                        },
                    ],
                }}
                items={items}
                loading={isLoading}
                isItemDisabled={getIsTableItemDisabled}
                loadingText="Loading"
                selectionType="multi"
                header={
                    <Header
                        variant="awsui-h1-sticky"
                        counter={renderCounter()}
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
                                <Button onClick={editSelectedProjectHandler} disabled={isDisabledEdit}>
                                    {t('common.edit')}
                                </Button>

                                <Button onClick={toggleDeleteConfirm} disabled={isDisabledDelete}>
                                    {t('common.delete')}
                                </Button>

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

            <ConfirmationDialog
                visible={showDeleteConfirm}
                onDiscard={toggleDeleteConfirm}
                onConfirm={deleteSelectedProjectsHandler}
            />
        </>
    );
};
