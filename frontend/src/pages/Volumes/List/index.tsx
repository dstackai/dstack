import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ButtonWithConfirmation, FormField, Header, Pagination, SelectCSD, Table, Toggle } from 'components';

import { useBreadcrumbs, useCollection } from 'hooks';
import { ROUTES } from 'routes';

import { useColumnsDefinitions, useFilters, useVolumesData, useVolumesDelete, useVolumesTableEmptyMessages } from './hooks';

import styles from './styles.module.scss';

export const VolumeList: React.FC = () => {
    const { t } = useTranslation();
    const {
        onlyActive,
        setOnlyActive,
        isDisabledClearFilter,
        clearFilters,
        projectOptions,
        selectedProject,
        setSelectedProject,
    } = useFilters();

    const { isDeleting, deleteVolumes } = useVolumesDelete();

    const { renderEmptyMessage, renderNoMatchMessage } = useVolumesTableEmptyMessages({
        clearFilters,
        isDisabledClearFilter,
    });

    const { data, isLoading, pagesCount, disabledNext, prevPage, nextPage, refreshList } = useVolumesData({
        project_name: selectedProject?.value ?? undefined,
        only_active: onlyActive,
    });

    const { columns } = useColumnsDefinitions();

    useBreadcrumbs([
        {
            text: t('volume.volumes'),
            href: ROUTES.VOLUMES.LIST,
        },
    ]);

    const { items, collectionProps, actions } = useCollection(data, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const deleteSelectedVolumes = () => {
        if (!selectedItems?.length) return;

        deleteVolumes([...selectedItems])
            .finally(() => {
                refreshList();
                actions.setSelectedItems([]);
            })
            .catch(console.log);
    };

    const isDisabledDeleteSelected = !selectedItems?.length || isDeleting;

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            stickyHeader={true}
            header={
                <Header
                    variant="awsui-h1-sticky"
                    actions={
                        <ButtonWithConfirmation
                            disabled={isDisabledDeleteSelected}
                            formAction="none"
                            onClick={deleteSelectedVolumes}
                            confirmTitle={t('volume.delete_volumes_confirm_title')}
                            confirmContent={t('volume.delete_volumes_confirm_message')}
                        >
                            {t('common.delete')}
                        </ButtonWithConfirmation>
                    }
                >
                    {t('volume.volumes')}
                </Header>
            }
            selectionType="multi"
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
                            {t('volume.active_only')}
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
                    disabled={isLoading || data.length === 0}
                    onPreviousPageClick={prevPage}
                    onNextPageClick={nextPage}
                />
            }
        />
    );
};
