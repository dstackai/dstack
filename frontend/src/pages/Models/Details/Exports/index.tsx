import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { TableProps } from 'components';
import { Alert, Header, ListEmptyMessage, NavigateLink, Table } from 'components';

import { useCollection } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';

import { TModelExport, TModelExportProject } from './helpers';
import { useModelExports } from './hooks';

import { IModelExtended } from '../../List/types';

// A row of the table: an export, and under it the projects that import the model through it
type TItem = TModelExport | TModelExportProject;

const isExport = (item: TItem): item is TModelExport => 'projects' in item;

type Props = {
    model: IModelExtended;
    // The user's projects and their import lists
    projects: IProject[];
    projectsImports: TProjectImports[];
};

export const ModelExports: React.FC<Props> = ({ model, projects, projectsImports }) => {
    const { t } = useTranslation();
    const { modelExports, isLoading, error } = useModelExports(model, projects, projectsImports);

    const [collapsedExports, setCollapsedExports] = useState<TModelExport['export_name'][]>([]);

    const columns: TableProps.ColumnDefinition<TItem>[] = [
        {
            id: 'name',
            header: t('models.exports.name'),
            cell: (item) => (isExport(item) ? item.export_name : null),
        },
        {
            id: 'project',
            header: t('models.project'),
            cell: (item) =>
                isExport(item) ? null : (
                    <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(item.project_name)}>{item.project_name}</NavigateLink>
                ),
        },
    ];

    const { items, collectionProps } = useCollection<TItem>(modelExports, {
        filtering: {
            empty: error ? (
                <Alert type="error">{t('common.server_error', { error: getServerError(error) })}</Alert>
            ) : (
                <ListEmptyMessage
                    title={t('models.exports.empty_message_title')}
                    message={t('models.exports.empty_message_text')}
                />
            ),
        },
    });

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            trackBy={(item) => (isExport(item) ? item.export_name : `${item.export_name}/${item.project_name}`)}
            // Exports are expanded until the user collapses them
            expandableRows={{
                getItemChildren: (item) => (isExport(item) ? item.projects : []),
                isItemExpandable: (item) => isExport(item) && item.projects.length > 0,
                expandedItems: items.filter(({ export_name }) => !collapsedExports.includes(export_name)),
                onExpandableItemToggle: ({ detail }) =>
                    setCollapsedExports((currentExports) =>
                        detail.expanded
                            ? currentExports.filter((exportName) => exportName !== detail.item.export_name)
                            : [...currentExports, detail.item.export_name],
                    ),
            }}
            loading={isLoading}
            loadingText={t('common.loading')}
            header={<Header>{t('models.exports.title')}</Header>}
        />
    );
};
