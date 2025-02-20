import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ButtonWithConfirmation, FormField, Header, Loader, SelectCSD, SpaceBetween, Table, Toggle } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetAllVolumesQuery } from 'services/volume';

import { useColumnsDefinitions, useFilters, useVolumesDelete, useVolumesTableEmptyMessages } from './hooks';

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

    const { data, isLoading, refreshList, isLoadingMore } = useInfiniteScroll<IVolume, TVolumesListRequestParams>({
        useLazyQuery: useLazyGetAllVolumesQuery,
        args: { project_name: selectedProject?.value ?? undefined, only_active: onlyActive, limit: DEFAULT_TABLE_PAGE_SIZE },

        getPaginationParams: (lastFleet) => ({
            prev_created_at: lastFleet.created_at,
            prev_id: lastFleet.id,
        }),
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
                        <SpaceBetween size="xs" direction="horizontal">
                            <ButtonWithConfirmation
                                disabled={isDisabledDeleteSelected}
                                formAction="none"
                                onClick={deleteSelectedVolumes}
                                confirmTitle={t('volume.delete_volumes_confirm_title')}
                                confirmContent={t('volume.delete_volumes_confirm_message')}
                            >
                                {t('common.delete')}
                            </ButtonWithConfirmation>

                            <Button
                                iconName="refresh"
                                disabled={isLoading}
                                ariaLabel={t('common.refresh')}
                                onClick={refreshList}
                            />
                        </SpaceBetween>
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
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
