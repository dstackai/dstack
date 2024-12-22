import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, FormField, Header, Pagination, SelectCSD, SpaceBetween, Table, Toggle } from 'components';

import { useBreadcrumbs, useCollection } from 'hooks';
import { ROUTES } from 'routes';

import { useColumnsDefinitions, useEmptyMessages, useFilters, useFleetsData } from './hooks';
import { useDeleteFleet } from './useDeletePoolInstance';

import styles from './styles.module.scss';

export const FleetList: React.FC = () => {
    const { t } = useTranslation();

    useBreadcrumbs([
        {
            text: t('navigation.fleets'),
            href: ROUTES.FLEETS.LIST,
        },
    ]);

    const {
        onlyActive,
        setOnlyActive,
        isDisabledClearFilter,
        clearFilters,
        projectOptions,
        selectedProject,
        setSelectedProject,
    } = useFilters();

    const { data, pagesCount, disabledNext, isLoading, nextPage, prevPage, refreshList } = useFleetsData({
        project_name: selectedProject?.value,
        only_active: onlyActive,
    });

    const isDisabledPagination = isLoading || data.length === 0;

    const { columns } = useColumnsDefinitions();
    const { deleteFleets, isDeleting } = useDeleteFleet();
    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({ clearFilters, isDisabledClearFilter });

    const { items, collectionProps } = useCollection<IFleet>(data, {
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

    const renderCounter = () => {
        if (!data?.length) return '';

        return `(${data.length})`;
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
                    counter={renderCounter()}
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
                    {t('navigation.fleets')}
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

                    <div className={styles.activeOnly}>
                        <Toggle onChange={({ detail }) => setOnlyActive(detail.checked)} checked={onlyActive}>
                            {t('fleets.active_only')}
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
