import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Header, ListEmptyMessage, NavigateLink, Pagination, Table } from 'components';

import { useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useGetProjectsQuery } from 'services/project';

export const UserProjectList: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramUserName = params.userName ?? '';

    const { isLoading, isFetching, data } = useGetProjectsQuery();

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage
                title={t('projects.empty_message_title')}
                message={t('projects.empty_message_text')}
            ></ListEmptyMessage>
        );
    };

    const filteredData = useMemo<IProject[]>(() => {
        if (!data) return [];

        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        return [...data]
            .filter((p) => p.owner.username === paramUserName)
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    }, [data]);

    const { items, collectionProps, paginationProps } = useCollection(filteredData, {
        filtering: {
            empty: renderEmptyMessage(),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    const renderCounter = () => {
        if (!filteredData?.length) return '';

        return `(${filteredData.length})`;
    };

    const columns = [
        {
            id: 'project_name',
            header: `${t('projects.edit.project_name')}`,
            cell: (project: IProject) => (
                <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(project.project_name)}>{project.project_name}</NavigateLink>
            ),
        },
    ];

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            loading={isLoading || isFetching}
            loadingText={t('common.loading')}
            header={
                <Header variant="awsui-h1-sticky" counter={renderCounter()}>
                    {t('users.projects')}
                </Header>
            }
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
        />
    );
};
