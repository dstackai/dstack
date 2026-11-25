import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, Button, Header, PropertyFilter, Table, Toggle } from 'components';

import { useBreadcrumbs, useCollection } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';

import { useModelListPreferences } from './Preferences/useModelListPreferences';
import { getImportedModelStatus, mergeModels } from '../helpers';
import { useProjectsImports, useRunModels } from '../hooks';
import { useColumnsDefinitions, useEmptyMessages, useFilters } from './hooks';
import { Preferences } from './Preferences';

import { IModelExtended } from './types';

import styles from './styles.module.scss';

export const List: React.FC = () => {
    const { t } = useTranslation();

    const {
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        filteringRequestParams,
        onlyActive,
        onChangeOnlyActive,
        filteringStatusType,
        handleLoadItems,
    } = useFilters();

    useBreadcrumbs([
        {
            text: t('navigation.models'),
            href: ROUTES.PROJECT.LIST,
        },
    ]);

    const { columns } = useColumnsDefinitions();
    const [preferences] = useModelListPreferences();

    // With `Active models` off, the list also has the models of the latest runs
    const {
        models: runModels,
        isFetching: isFetchingRuns,
        error,
        refetch: refetchRuns,
    } = useRunModels(filteringRequestParams, () => !onlyActive);

    const {
        projectsImports,
        isFetching: isFetchingImports,
        refetch: refetchImports,
    } = useProjectsImports(filteringRequestParams);

    const models = useMemo(() => {
        // A failed runs request shows its error, not the part of the models that was loaded
        if (error) {
            return [];
        }

        const mergedModels = mergeModels(runModels, projectsImports);

        // With `Active models` on, only the active runs are read, and an imported model is active while a service serves it
        return mergedModels.filter((model) => !onlyActive || model.run || getImportedModelStatus(model) === 'running');
    }, [error, runModels, projectsImports, onlyActive]);

    const isLoading = isFetchingRuns || isFetchingImports;

    const refreshModels = () => {
        refetchRuns();
        refetchImports();
    };

    const isDisabledClearFilter = !propertyFilterQuery.tokens.length;

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        clearFilter,
        isDisabledClearFilter,
    });

    const { items, collectionProps } = useCollection<IModelExtended>(models, {
        filtering: {
            empty: error ? (
                <Alert type="error">{t('common.server_error', { error: getServerError(error) })}</Alert>
            ) : (
                renderEmptyMessage()
            ),
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
                            disabled={isLoading}
                            ariaLabel={t('common.refresh')}
                            onClick={refreshModels}
                        />
                    }
                >
                    {t('navigation.models')}
                </Header>
            }
            filter={
                <div className={styles.selectFilters}>
                    <div className={styles.propertyFilter}>
                        <PropertyFilter
                            query={propertyFilterQuery}
                            onChange={onChangePropertyFilter}
                            expandToViewport
                            hideOperations
                            i18nStrings={{
                                clearFiltersText: t('common.clearFilter'),
                                filteringAriaLabel: t('projects.run.filter_property_placeholder'),
                                filteringPlaceholder: t('projects.run.filter_property_placeholder'),
                                operationAndText: 'and',
                                enteredTextLabel: (value) => `Use: ${value}`,
                            }}
                            filteringOptions={filteringOptions}
                            filteringProperties={filteringProperties}
                            filteringStatusType={filteringStatusType}
                            onLoadItems={handleLoadItems}
                        />
                    </div>

                    <div className={styles.activeOnly}>
                        <Toggle onChange={onChangeOnlyActive} checked={onlyActive}>
                            {t('models.active_only')}
                        </Toggle>
                    </div>
                </div>
            }
            preferences={<Preferences />}
        />
    );
};
