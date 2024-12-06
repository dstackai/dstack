import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { sortBy as _sortBy } from 'lodash';

import { Button, FormField, Header, Pagination, SelectCSD, Table } from 'components';

import { useBreadcrumbs, useCollection } from 'hooks';
import { getExtendedModelFromRun } from 'libs/run';
import { ROUTES } from 'routes';
import { useGetRunsQuery } from 'services/run';

import { unfinishedRuns } from 'pages/Runs/constants';

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

    const { data, isLoading, isFetching, refetch } = useGetRunsQuery({
        project_name: selectedProject?.value,
    });

    useBreadcrumbs([
        {
            text: t('navigation.models'),
            href: ROUTES.PROJECT.LIST,
        },
    ]);

    const { columns } = useColumnsDefinitions();
    const [preferences] = useModelListPreferences();

    const sortedData = useMemo<IModelExtended[]>(() => {
        if (!data) return [];

        return (
            _sortBy<IRun>(data, [(i) => -i.submitted_at])
                // Should show models of active runs only
                .filter((run) => unfinishedRuns.includes(run.status) && run.service?.model)
                .reduce<IModelExtended[]>((acc, run) => {
                    const model = getExtendedModelFromRun(run);

                    if (model) acc.push(model);

                    return acc;
                }, [])
        );
    }, [data]);

    const clearFilter = () => {
        clearSelected();
    };

    const isDisabledClearFilter = !selectedProject;

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        clearFilter,
        isDisabledClearFilter,
    });

    const { items, collectionProps, paginationProps } = useCollection<IModelExtended>(sortedData ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            columnDefinitions={columns}
            items={items}
            loading={isLoading || isFetching}
            loadingText={t('common.loading')}
            stickyHeader={true}
            columnDisplay={preferences.contentDisplay}
            header={
                <Header
                    variant="awsui-h1-sticky"
                    actions={
                        <Button
                            iconName="refresh"
                            disabled={isLoading || isFetching}
                            ariaLabel={t('common.refresh')}
                            onClick={refetch}
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
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
            preferences={<Preferences />}
        />
    );
};
