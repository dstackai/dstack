import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { StatusIndicatorProps } from '@cloudscape-design/components';

import {
    Box,
    Button,
    ColumnLayout,
    Container,
    ContentLayout,
    DetailsHeader,
    Header,
    ListEmptyMessage,
    Loader,
    NavigateLink,
    Pagination,
    SpaceBetween,
    StatusIndicator,
    Table,
    TextFilter,
} from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs } from 'hooks';
import { useCollection } from 'hooks';
import { getRepoDisplayName } from 'libs/repo';
import { ROUTES } from 'routes';
import { useGetProjectRepoQuery, useGetProjectRunsQuery } from 'services/project';

import { RepoTypeEnum } from '../types';

export const RepositoryDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramRepoId = params.repoId ?? '';

    const { data: repoData, isLoading: isLoadingRepo } = useGetProjectRepoQuery({
        name: paramProjectName,
        repo_id: paramRepoId,
    });

    const { data, isLoading } = useGetProjectRunsQuery({
        name: paramProjectName,
        repo_id: paramRepoId,
    });

    const displayRepoName = repoData ? getRepoDisplayName(repoData) : 'Loading...';

    useBreadcrumbs([
        {
            text: t('navigation.projects'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            text: t('projects.repositories'),
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            text: displayRepoName,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(paramProjectName, paramRepoId),
        },
    ]);

    const getStatusIconType = (status: IRun['status']): StatusIndicatorProps['type'] => {
        switch (status) {
            case 'failed':
                return 'error';
            case 'aborted':
            case 'stopped':
                return 'stopped';
            case 'done':
                return 'success';
            case 'running':
            case 'uploading':
            case 'downloading':
                return 'in-progress';
            case 'submitted':
            case 'pending':
                return 'pending';
            default:
                return 'stopped';
        }
    };

    const COLUMN_DEFINITIONS = [
        {
            id: 'run_name',
            header: t('projects.run.run_name'),
            cell: (item: IRun) =>
                // TODO revert link after adding run details page
                // <NavigateLink href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRepoId, item.run_name)}>
                //     {item.run_name}
                // </NavigateLink>
                item.run_name,
        },
        {
            id: 'workflow_name',
            header: `${t('projects.run.workflow_name')}/${t('projects.run.provider_name')}`,
            cell: (item: IRun) => item.workflow_name ?? item.provider_name,
        },
        {
            id: 'status',
            header: t('projects.run.status'),
            cell: (item: IRun) => (
                <StatusIndicator type={getStatusIconType(item.status)}>
                    {t(`projects.run.statuses.${item.status}`)}
                </StatusIndicator>
            ),
        },
        {
            id: 'submitted_at',
            header: t('projects.run.submitted_at'),
            cell: (item: IRun) => format(new Date(item.submitted_at), DATE_TIME_FORMAT),
        },
        // {
        //     id: 'artifacts',
        //     header: t('projects.run.artifacts'),
        //     cell: (item: IRun) => item.artifact_heads?.length ?? '-',
        // },
    ];

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.run.empty_message_title')} message={t('projects.run.empty_message_text')} />
        );
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('projects.run.nomatch_message_title')} message={t('projects.run.nomatch_message_text')}>
                <Button onClick={onClearFilter}>{t('common.clearFilter')}</Button>
            </ListEmptyMessage>
        );
    };

    const { items, actions, filteredItemsCount, collectionProps, filterProps, paginationProps } = useCollection(data ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(() => actions.setFiltering('')),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    return (
        <ContentLayout header={<DetailsHeader title={displayRepoName} />}>
            <SpaceBetween size="l">
                {isLoadingRepo && !repoData && (
                    <Container>
                        <Loader />
                    </Container>
                )}

                {repoData && (
                    <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                        <ColumnLayout columns={4} variant="text-grid">
                            <div>
                                <Box variant="awsui-key-label">{t('projects.repo.card.last_run')}</Box>
                                <div>{format(new Date(repoData.last_run_at), DATE_TIME_FORMAT)}</div>
                            </div>

                            {repoData.repo_info.repo_type === RepoTypeEnum.LOCAL && (
                                <div>
                                    <Box variant="awsui-key-label">{t('projects.repo.card.directory')}</Box>
                                    <div>{repoData.repo_info.repo_dir}</div>
                                </div>
                            )}
                        </ColumnLayout>
                    </Container>
                )}

                <Table
                    {...collectionProps}
                    columnDefinitions={COLUMN_DEFINITIONS}
                    items={items}
                    loading={isLoading}
                    loadingText={t('common.loading')}
                    selectionType="multi"
                    stickyHeader={true}
                    header={
                        <Header
                            actions={
                                <SpaceBetween size="xs" direction="horizontal">
                                    {/*<Button formAction="none" disabled>*/}
                                    {/*    {t('common.stop')}*/}
                                    {/*</Button>*/}

                                    {/*<Button formAction="none" disabled>*/}
                                    {/*    {t('common.delete')}*/}
                                    {/*</Button>*/}
                                </SpaceBetween>
                            }
                        >
                            {t('projects.runs')}
                        </Header>
                    }
                    filter={
                        <TextFilter
                            {...filterProps}
                            filteringPlaceholder={t('projects.run.search_placeholder')}
                            countText={t('common.match_count_with_value', { count: filteredItemsCount })}
                            disabled={isLoading}
                        />
                    }
                    pagination={<Pagination {...paginationProps} disabled={isLoading} />}
                />
            </SpaceBetween>
        </ContentLayout>
    );
};
