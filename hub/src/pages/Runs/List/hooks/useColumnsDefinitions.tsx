import React from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { NavigateLink, StatusIndicator } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns = [
        {
            id: 'run_name',
            header: t('projects.run.run_name'),
            cell: (item: IRunListItem) => {
                return item.repo_id !== null ? (
                    <NavigateLink
                        href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(item.project, item.repo_id, item.run_head.run_name)}
                    >
                        {item.run_head.run_name}
                    </NavigateLink>
                ) : (
                    item.run_head.run_name
                );
            },
        },
        {
            id: 'project',
            header: `${t('projects.run.project')}`,
            cell: (item: IRunListItem) => item.project,
        },
        {
            id: 'repo',
            header: `${t('projects.run.repo')}`,
            cell: (item: IRunListItem) => {
                return item.repo_id !== null ? (
                    <NavigateLink href={ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(item.project, item.repo_id)}>
                        {item.repo_id}
                    </NavigateLink>
                ) : (
                    item.repo_id ?? ''
                );
            },
        },
        {
            id: 'configuration',
            header: `${t('projects.run.configuration')}`,
            cell: (item: IRunListItem) => item.run_head.job_heads?.[0].configuration_path,
        },
        {
            id: 'instance',
            header: `${t('projects.run.instance')}`,
            cell: (item: IRunListItem) => item.run_head.job_heads?.[0].instance_type,
        },
        {
            id: 'hub_user_name',
            header: `${t('projects.run.hub_user_name')}`,
            cell: (item: IRunListItem) => item.run_head.hub_user_name,
        },
        {
            id: 'status',
            header: t('projects.run.status'),
            cell: (item: IRunListItem) => (
                <StatusIndicator type={getStatusIconType(item.run_head.status)}>
                    {t(`projects.run.statuses.${item.run_head.status}`)}
                </StatusIndicator>
            ),
        },
        {
            id: 'submitted_at',
            header: t('projects.run.submitted_at'),
            cell: (item: IRunListItem) => format(new Date(item.run_head.submitted_at), DATE_TIME_FORMAT),
        },
    ];

    return { columns } as const;
};
