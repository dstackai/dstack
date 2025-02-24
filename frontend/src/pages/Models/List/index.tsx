import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, FormField, Header, Loader, SelectCSD, Table } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetModelsQuery } from 'services/run';

import { useModelListPreferences } from './Preferences/useModelListPreferences';
import { useColumnsDefinitions, useEmptyMessages, useFilters } from './hooks';
import { Preferences } from './Preferences';

import { IModelExtended } from './types';

import styles from './styles.module.scss';

export const List: React.FC = () => {
    const { t } = useTranslation();

    const { projectOptions, selectedProject, setSelectedProject, clearSelected } = useFilters({
        projectSearchKey: 'project',
    });

    useBreadcrumbs([
        {
            text: t('navigation.models'),
            href: ROUTES.PROJECT.LIST,
        },
    ]);

    const { columns } = useColumnsDefinitions();
    const [preferences] = useModelListPreferences();

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IModelExtended, TRunsRequestParams>({
        useLazyQuery: useLazyGetModelsQuery,
        args: { project_name: selectedProject?.value, limit: DEFAULT_TABLE_PAGE_SIZE },

        getPaginationParams: (lastModel) => ({ prev_submitted_at: lastModel.submitted_at }),
    });

    const clearFilter = () => {
        clearSelected();
    };

    const isDisabledClearFilter = !selectedProject;

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        clearFilter,
        isDisabledClearFilter,
    });

    const { items, collectionProps } = useCollection<IModelExtended>(data, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        selection: {},
    });

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            stickyHeader={true}
            columnDisplay={preferences.contentDisplay}
            header={
                <Header
                    variant="awsui-h1-sticky"
                    actions={
                        <Button
                            iconName="refresh"
                            disabled={isLoading || isLoadingMore}
                            ariaLabel={t('common.refresh')}
                            onClick={refreshList}
                        />
                    }
                >
                    {t('navigation.models')}
                </Header>
            }
            filter={
                <div className={styles.selectFilters}>
                    <div className={styles.select}>
                        <FormField label={t('projects.run.project')}>
                            <SelectCSD
                                disabled={!projectOptions?.length}
                                options={projectOptions}
                                selectedOption={selectedProject}
                                onChange={(event) => {
                                    setSelectedProject(event.detail.selectedOption);
                                }}
                                placeholder={t('projects.run.project_placeholder')}
                                expandToViewport={true}
                                filteringType="auto"
                            />
                        </FormField>
                    </div>

                    <div className={styles.clear}>
                        <Button disabled={isDisabledClearFilter} formAction="none" onClick={clearSelected}>
                            {t('common.clearFilter')}
                        </Button>
                    </div>
                </div>
            }
            preferences={<Preferences />}
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
