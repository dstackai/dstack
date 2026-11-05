import React from 'react';
import { useListener } from 'react-bus';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { product } from 'product';
import Button from '@cloudscape-design/components/button';

import { Header, Loader, Table } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetAllEventsQuery } from 'services/events';

import { useColumnsDefinitions } from 'pages/Events/List/hooks/useColumnDefinitions';
import { getEventsOrderSearchParams, useEventsOrder } from 'pages/Events/List/hooks/useEventsOrder';

import { RUN_DETAILS_REFRESH_LIST_EVENT } from '../../constants';

export const EventsList = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramRunId = params.runId ?? '';
    const navigate = useNavigate();

    const { ascending, sortingProps } = useEventsOrder();

    const { data, isLoading, isLoadingMore, refreshList } = useInfiniteScroll<IEvent, TEventListRequestParams>({
        useLazyQuery: useLazyGetAllEventsQuery,
        args: { limit: DEFAULT_TABLE_PAGE_SIZE, within_runs: [paramRunId], ascending },

        getPaginationParams: (lastEvent) => ({
            prev_recorded_at: lastEvent.recorded_at,
            prev_id: lastEvent.id,
        }),
    });

    useListener(RUN_DETAILS_REFRESH_LIST_EVENT, refreshList);

    const { items, collectionProps } = useCollection<IEvent>(data, {
        selection: {},
    });

    const goToFullView = () => {
        const searchParams = new URLSearchParams({ within_runs: paramRunId, ...getEventsOrderSearchParams(ascending) });
        navigate(`${ROUTES.EVENTS.LIST}?${searchParams}`);
    };

    const { columns } = useColumnsDefinitions();

    return (
        <Table
            {...collectionProps}
            {...sortingProps}
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            header={
                <Header actions={product.hasEvents && <Button onClick={goToFullView}>{t('common.full_view')}</Button>}>
                    {t('navigation.events')}
                </Header>
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
