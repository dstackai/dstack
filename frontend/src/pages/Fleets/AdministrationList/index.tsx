import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Container, ContentLayout, DetailsHeader, Header, Loader, Pagination, Table, Toggle } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useCollection } from 'hooks';
import { useLazyGetPoolsInstancesQuery } from 'services/pool';

import { useEmptyMessages } from '../List/hooks';
import { useColumnsDefinitions, useFilters } from './hooks';

import styles from '../List/styles.module.scss';

export const AdministrationFleetsList: React.FC = () => {
    const { t } = useTranslation();
    const [data, setData] = useState<IInstanceListItem[]>([]);
    const [pagesCount, setPagesCount] = useState<number>(1);
    const [disabledNext, setDisabledNext] = useState(false);

    const { onlyActive, setOnlyActive, isDisabledClearFilter, clearFilters } = useFilters();

    const [getPools, { isLoading, isFetching }] = useLazyGetPoolsInstancesQuery();
    const isDisabledPagination = isLoading || isFetching || data.length === 0;

    const getPoolsRequest = (params?: Partial<TPoolInstancesRequestParams>) => {
        return getPools({
            only_active: onlyActive,
            limit: DEFAULT_TABLE_PAGE_SIZE,
            ...params,
        }).unwrap();
    };

    useEffect(() => {
        getPoolsRequest().then((result) => {
            setPagesCount(1);
            setDisabledNext(false);
            setData(result);
        });
    }, [onlyActive]);

    const { columns } = useColumnsDefinitions();
    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages();

    const nextPage = async () => {
        if (data.length === 0 || disabledNext) {
            return;
        }

        try {
            const result = await getPoolsRequest({
                prev_created_at: data[data.length - 1].created,
                prev_id: data[data.length - 1].id,
            });

            if (result.length > 0) {
                setPagesCount((count) => count + 1);
                setData(result);
            } else {
                setDisabledNext(true);
            }
        } catch (e) {
            console.log(e);
        }
    };

    const prevPage = async () => {
        if (pagesCount === 1) {
            return;
        }

        try {
            const result = await getPoolsRequest({
                prev_created_at: data[0].created,
                prev_id: data[0].id,
                ascending: true,
            });

            setDisabledNext(false);

            if (result.length > 0) {
                setPagesCount((count) => count - 1);
                setData(result);
            } else {
                setPagesCount(1);
            }
        } catch (e) {
            console.log(e);
        }
    };

    const { items, collectionProps } = useCollection<IInstanceListItem>(data, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    const renderCounter = () => {
        if (!data?.length) return '';

        return `(${data.length})`;
    };

    return (
        <ContentLayout header={<DetailsHeader title={t('navigation.fleets')} />}>
            {isLoading && (
                <Container>
                    <Loader />
                </Container>
            )}

            {!isLoading && (
                <Table
                    {...collectionProps}
                    columnDefinitions={columns}
                    items={items}
                    loading={isLoading}
                    loadingText={t('common.loading')}
                    stickyHeader={true}
                    header={<Header counter={renderCounter()}>{t('fleets.instances.title')}</Header>}
                    filter={
                        <div className={styles.filters}>
                            <div className={styles.activeOnly}>
                                <Toggle onChange={({ detail }) => setOnlyActive(detail.checked)} checked={onlyActive}>
                                    {t('fleets.active_only')}
                                </Toggle>
                            </div>

                            <Button formAction="none" onClick={clearFilters} disabled={isDisabledClearFilter}>
                                {t('common.clearFilter')}
                            </Button>
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
            )}
        </ContentLayout>
    );
};
