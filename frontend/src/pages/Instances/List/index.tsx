import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, FormField, Header, Pagination, SelectCSD, SpaceBetween, Table, Toggle } from 'components';

import { useBreadcrumbs } from 'hooks';
import { useCollection } from 'hooks';
import { ROUTES } from 'routes';

import { useActions } from './hooks/useActions';
import { useColumnsDefinitions } from './hooks/useColumnDefinitions';
import { useEmptyMessages } from './hooks/useEmptyMessage';
import { useFilters } from './hooks/useFilters';
import { useInstanceListData } from './hooks/useInstanceListData';

import styles from './styles.module.scss';

export const List: React.FC = () => {
    const { t } = useTranslation();

    useBreadcrumbs([
        {
            text: t('navigation.instances'),
            href: ROUTES.INSTANCES.LIST,
        },
    ]);

    const { columns } = useColumnsDefinitions();

    const {
        onlyActive,
        setOnlyActive,
        isDisabledClearFilter,
        clearFilters,
        projectOptions,
        selectedProject,
        setSelectedProject,
        selectedFleet,
    } = useFilters();

    const params = useMemo<TInstanceListRequestParams>(() => {
        return {
            project_names: selectedProject?.value ? [selectedProject.value] : undefined,
            only_active: onlyActive,
            fleet_ids: selectedFleet?.value ? [selectedFleet.value] : undefined,
        };
    }, [selectedProject, selectedFleet, onlyActive]);

    const { data, pagesCount, disabledNext, isLoading, nextPage, prevPage, refreshList } = useInstanceListData(params);

    const isDisabledPagination = isLoading || data.length === 0;

    const { deleteFleets, isDeleting } = useActions();

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({ clearFilters, isDisabledClearFilter });

    const { items, collectionProps } = useCollection<IInstance>(data, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const isDisabledDeleteButton = !selectedItems?.length || isDeleting;

    const deleteClickHandle = () => {
        if (!selectedItems?.length) return;

        deleteFleets([...selectedItems]).catch(console.log);
    };

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            stickyHeader={true}
            selectionType="multi"
            header={
                <Header
                    variant="awsui-h1-sticky"
                    actions={
                        <SpaceBetween size="xs" direction="horizontal">
                            <Button formAction="none" onClick={deleteClickHandle} disabled={isDisabledDeleteButton}>
                                {t('common.delete')}
                            </Button>

                            <Button
                                iconName="refresh"
                                disabled={isLoading}
                                ariaLabel={t('common.refresh')}
                                onClick={refreshList}
                            />
                        </SpaceBetween>
                    }
                >
                    {t('navigation.instances')}
                </Header>
            }
            filter={
                <div className={styles.filters}>
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

                    <div className={styles.select}>
                        <FormField label={t('fleets.fleet')}>
                            <SelectCSD
                                disabled
                                options={[...(selectedFleet ? [selectedFleet] : [])]}
                                selectedOption={selectedFleet}
                                placeholder={t('fleets.fleet_placeholder')}
                                expandToViewport={true}
                                filteringType="auto"
                            />
                        </FormField>
                    </div>

                    <div className={styles.activeOnly}>
                        <Toggle onChange={({ detail }) => setOnlyActive(detail.checked)} checked={onlyActive}>
                            {t('fleets.instances.active_only')}
                        </Toggle>
                    </div>

                    <div className={styles.clear}>
                        <Button formAction="none" onClick={clearFilters} disabled={isDisabledClearFilter}>
                            {t('common.clearFilter')}
                        </Button>
                    </div>
                </div>
            }
            pagination={
                <Pagination
                    currentPageIndex={pagesCount}
                    pagesCount={pagesCount}
                    openEnd={!disabledNext}
                    disabled={isDisabledPagination}
                    onPreviousPageClick={prevPage}
                    onNextPageClick={nextPage}
                />
            }
        />
    );
};
