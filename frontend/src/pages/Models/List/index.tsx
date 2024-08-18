import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { sortBy as _sortBy } from 'lodash';

import { Header, Pagination, Table } from 'components';
import { useProjectDropdown } from 'layouts/AppLayout/hooks';

import { useCollection } from 'hooks';
import { getExtendedModelFromRun } from 'libs/run';
import { useGetRunsQuery } from 'services/run';

import { useModelListPreferences } from './Preferences/useModelListPreferences';
import { unfinishedRuns } from '../../Runs/constants';
import { useColumnsDefinitions, useEmptyMessages } from './hooks';
import { Preferences } from './Preferences';

import { IModelExtended } from './types';

export const List: React.FC = () => {
    const { t } = useTranslation();
    const { selectedProject } = useProjectDropdown();

    const { data, isLoading } = useGetRunsQuery();

    const { columns } = useColumnsDefinitions();
    const [preferences] = useModelListPreferences();

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages();

    const sortedData = useMemo<IModelExtended[]>(() => {
        if (!data) return [];

        return (
            _sortBy<IRun>(data, [(i) => -i.submitted_at])
                // Should show models of active runs only
                .filter((run) => unfinishedRuns.includes(run.status))
                .reduce<IModelExtended[]>((acc, run) => {
                    const model = getExtendedModelFromRun(run);

                    if (model) acc.push(model);

                    return acc;
                }, [])
        );
    }, [data]);

    const { items, collectionProps, paginationProps } = useCollection<IModelExtended>(sortedData ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),

            filteringFunction: (modelItem) => {
                return !(selectedProject && modelItem.project_name !== selectedProject);
            },
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
            loading={isLoading}
            loadingText={t('common.loading')}
            stickyHeader={true}
            columnDisplay={preferences.contentDisplay}
            header={<Header variant="awsui-h1-sticky">{t('navigation.models')}</Header>}
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
            preferences={<Preferences />}
        />
    );
};
