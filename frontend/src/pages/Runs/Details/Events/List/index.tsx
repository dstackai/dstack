import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Header, Loader, Table } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useCollection, useInfiniteScroll } from 'hooks';
import { useLazyGetAllEventsQuery } from 'services/events';

import { useColumnsDefinitions } from 'pages/Events/List/hooks/useColumnDefinitions';

export const EventsList = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramRunId = params.runId ?? '';

    const { data, isLoading, isLoadingMore } = useInfiniteScroll<IEvent, TEventListRequestParams>({
        useLazyQuery: useLazyGetAllEventsQuery,
        args: { limit: DEFAULT_TABLE_PAGE_SIZE, target_runs: [paramRunId] },

        getPaginationParams: (lastEvent) => ({
            prev_recorded_at: lastEvent.recorded_at,
            prev_id: lastEvent.id,
        }),
    });

    const { items, collectionProps } = useCollection<IEvent>(data, {
        selection: {},
    });

    const { columns } = useColumnsDefinitions();

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            header={<Header>{t('navigation.events')}</Header>}
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
