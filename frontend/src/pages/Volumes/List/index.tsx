import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Header, Pagination, SpaceBetween, Table, Toggle } from 'components';
import { useProjectDropdown } from 'layouts/AppLayout/hooks';

import { useCollection } from 'hooks';

import { useColumnsDefinitions, useFilters, useVolumesData, useVolumesTableEmptyMessages } from './hooks';

import styles from '../../Fleets/List/styles.module.scss';

export const VolumeList: React.FC = () => {
    const { t } = useTranslation();
    const { renderEmptyMessage, renderNoMatchMessage } = useVolumesTableEmptyMessages();
    const { selectedProject } = useProjectDropdown();

    const { onlyActive, setOnlyActive, isDisabledClearFilter, clearFilters } = useFilters();

    const { data, isLoading, pagesCount, disabledNext, prevPage, nextPage } = useVolumesData({
        project_name: selectedProject ?? undefined,
        only_active: onlyActive,
    });

    const { columns } = useColumnsDefinitions();

    const { items, actions, collectionProps } = useCollection(data, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(() => actions.setFiltering('')),
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
            header={<Header>{t('volume.volumes')}</Header>}
            filter={
                <div className={styles.filters}>
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
                    disabled={isLoading || data.length === 0}
                    onPreviousPageClick={prevPage}
                    onNextPageClick={nextPage}
                />
            }
        />
    );
};
