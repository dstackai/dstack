import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button, Cards, Header, ListEmptyMessage, NavigateLink, Pagination, SpaceBetween, TextFilter } from 'components';

import { useBreadcrumbs, useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useGetProjectsQuery } from 'services/project';

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
    const { isLoading, data } = useGetProjectsQuery();
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

    const renderCounter = () => {
        if (!data?.length) return '';

        return `(${data.length})`;
    };

    const getProjectSettings = (project: IProject) => {
        switch (project.backend.type) {
            case 'aws':
                return (
                    <div>
                        <ProjectSettingsNode settingsKey="Region" settingsValue={project.backend.region_name_title} />
                        <ProjectSettingsNode settingsKey="Bucket" settingsValue={project.backend.s3_bucket_name} />
                    </div>
                );
            case 'azure':
                return (
                    <div>
                        <ProjectSettingsNode settingsKey="Location" settingsValue={project.backend.location} />
                        <ProjectSettingsNode settingsKey="Storage account" settingsValue={project.backend.storage_account} />
                    </div>
                );
            case 'gcp':
                return (
                    <div>
                        <ProjectSettingsNode settingsKey="Region" settingsValue={project.backend.region} />
                        <ProjectSettingsNode settingsKey="Bucket" settingsValue={project.backend.bucket_name} />
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
                loadingText="Loading"
                header={
                    <Header
                        variant="awsui-h1-sticky"
                        counter={renderCounter()}
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
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
