import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import Button from '@cloudscape-design/components/button';

import { Header, Loader, Table } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useCollection, useInfiniteScroll } from 'hooks';
import { useLazyGetAllEventsQuery } from 'services/events';

import { useColumnsDefinitions } from 'pages/Events/List/hooks/useColumnDefinitions';

import { ROUTES } from '../../../../../routes';
import { useGetRunQuery } from '../../../../../services/run';

export const EventsList = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunId = params.runId ?? '';
    const paramJobName = params.jobName ?? '';
    const navigate = useNavigate();

    const { data: runData, isLoading: isLoadingRun } = useGetRunQuery({
        project_name: paramProjectName,
        id: paramRunId,
    });

    const jobId = useMemo<string | void>(() => {
        if (!runData) return;

        return runData.jobs.find((job) => job.job_spec.job_name === paramJobName)?.job_submissions?.[0]?.id;
    }, [runData]);

    const { data, isLoading, isLoadingMore } = useInfiniteScroll<IEvent, TEventListRequestParams>({
        useLazyQuery: useLazyGetAllEventsQuery,
        args: { limit: DEFAULT_TABLE_PAGE_SIZE, target_jobs: jobId ? [jobId] : undefined },
        skip: !jobId,

        getPaginationParams: (lastEvent) => ({
            prev_recorded_at: lastEvent.recorded_at,
            prev_id: lastEvent.id,
        }),
    });

    const goToFullView = () => {
        navigate(ROUTES.EVENTS.LIST + `?target_jobs=${jobId}`);
    };

    const { items, collectionProps } = useCollection<IEvent>(data, {
        selection: {},
    });

    const { columns } = useColumnsDefinitions();

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            loading={isLoading || isLoadingRun}
            loadingText={t('common.loading')}
            header={
                <Header
                    actions={
                        <Button onClick={goToFullView} disabled={!jobId}>
                            {t('common.full_view')}
                        </Button>
                    }
                >
                    {t('navigation.events')}
                </Header>
            }
            footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
        />
    );
};
