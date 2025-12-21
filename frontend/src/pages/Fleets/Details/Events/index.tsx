import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import Button from '@cloudscape-design/components/button';

import { Header, Loader, Table } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetAllEventsQuery } from 'services/events';

import { useColumnsDefinitions } from 'pages/Events/List/hooks/useColumnDefinitions';

export const EventsList = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramFleetId = params.fleetId ?? '';
    const navigate = useNavigate();

    const { data, isLoading, isLoadingMore } = useInfiniteScroll<IEvent, TEventListRequestParams>({
        useLazyQuery: useLazyGetAllEventsQuery,
        args: { limit: DEFAULT_TABLE_PAGE_SIZE, within_fleets: [paramFleetId] },

        getPaginationParams: (lastEvent) => ({
            prev_recorded_at: lastEvent.recorded_at,
            prev_id: lastEvent.id,
        }),
    });

    const { items, collectionProps } = useCollection<IEvent>(data, {
        selection: {},
    });

    const goToFullView = () => {
        navigate(ROUTES.EVENTS.LIST + `?within_fleets=${paramFleetId}`);
    };

    const { columns } = useColumnsDefinitions();

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            header={
                <Header actions={<Button onClick={goToFullView}>{t('common.full_view')}</Button>}>
                    {t('navigation.events')}
                </Header>
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
