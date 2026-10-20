import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Button, ListEmptyMessage, Loader, NavigateLink, Table } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useAppSelector, useBreadcrumbs, useCollection, useInfiniteScroll } from 'hooks';
import { ROUTES } from 'routes';
import { useLazyGetProjectsQuery } from 'services/project';

import { selectUserData } from 'App/slice';
import { useCheckAvailableProjectPermission } from 'pages/Project/hooks/useCheckAvailableProjectPermission';

export const UserProjectList: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramUserName = params.userName ?? '';
    const navigate = useNavigate();
    const userData = useAppSelector(selectUserData);
    const isCurrentUser = userData?.username === paramUserName;
    const { isAvailableProjectManaging } = useCheckAvailableProjectPermission();

    const { data, isLoading, isLoadingMore } = useInfiniteScroll<IProject, TGetProjectListParams>({
        useLazyQuery: useLazyGetProjectsQuery,
        args: { username: paramUserName, limit: DEFAULT_TABLE_PAGE_SIZE },
        getPaginationParams: (project) => ({
            prev_created_at: project.created_at,
            prev_id: project.project_id,
        }),
    });

    useBreadcrumbs([
        {
            text: t('navigation.account'),
            href: ROUTES.USER.LIST,
        },
        {
            text: paramUserName,
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
        {
            text: t('users.projects'),
            href: ROUTES.USER.PROJECTS.FORMAT(paramUserName),
        },
    ]);

    const renderEmptyMessage = (): React.ReactNode => {
        if (isLoading) return null;

        return (
            <ListEmptyMessage title={t('projects.empty_message_title')} message={t('users.projects_table.empty_message')}>
                {isCurrentUser && isAvailableProjectManaging && (
                    <Button onClick={() => navigate(ROUTES.PROJECT.ADD)}>{t('common.create')}</Button>
                )}
            </ListEmptyMessage>
        );
    };

    const { items, collectionProps } = useCollection(data, {
        filtering: {
            empty: renderEmptyMessage(),
        },
        selection: {},
    });

    const columns = [
        {
            id: 'project_name',
            header: t('users.projects_table.project'),
            cell: (project: IProject) => (
                <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(project.project_name)}>{project.project_name}</NavigateLink>
            ),
        },
        {
            id: 'role',
            header: t('users.projects_table.role'),
            cell: (project: IProject) => {
                if (project.owner.username === paramUserName) return t('projects.edit.owner');

                const member = project.members.find(({ user }) => user.username === paramUserName);
                return member ? t(`roles.${member.project_role}`) : '-';
            },
        },
    ];

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            footer={isLoadingMore ? <Loader padding={{ vertical: 'm' }} /> : undefined}
        />
    );
};
