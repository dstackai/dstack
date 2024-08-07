import React from 'react';
import { useTranslation } from 'react-i18next';
import { get as _get } from 'lodash';
import { format } from 'date-fns';

import { NavigateLink, StatusIndicator } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { getRepoNameFromRun, getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns = [
        {
            id: 'run_name',
            header: t('projects.run.run_name'),
            cell: (item: IRun) => {
                return item.id !== null ? (
                    <NavigateLink
                        href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(
                            item.project_name,
                            item.run_spec.run_name ?? 'No run name',
                        )}
                    >
                        {item.run_spec.run_name}
                    </NavigateLink>
                ) : (
                    item.run_spec.run_name
                );
            },
        },
        {
            id: 'project',
            header: `${t('projects.run.project')}`,
            cell: (item: IRun) => item.project_name,
        },
        {
            id: 'repo',
            header: `${t('projects.run.repo')}`,
            cell: (item: IRun) => getRepoNameFromRun(item),
        },
        {
            id: 'hub_user_name',
            header: `${t('projects.run.hub_user_name')}`,
            cell: (item: IRun) => item.user,
        },
        {
            id: 'submitted_at',
            header: t('projects.run.submitted_at'),
            cell: (item: IRun) => format(new Date(item.submitted_at), DATE_TIME_FORMAT),
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
            id: 'cost',
            header: `${t('projects.run.cost')}`,
            cell: (item: IRun) => {
                return `$${item.cost}`;
            },
        },
        {
            id: 'resources',
            header: `${t('projects.run.resources')}`,
            cell: (item: IRun) => item.latest_job_submission?.job_provisioning_data?.instance_type?.resources?.description,
        },
        {
            id: 'spot',
            header: `${t('projects.run.spot')}`,
            cell: (item: IRun) => {
                if (item.latest_job_submission?.job_provisioning_data?.instance_type?.resources?.spot) {
                    return t('common.yes');
                }

                return t('common.no');
            },
        },
        {
            id: 'price',
            header: `${t('projects.run.price')}`,
            cell: (item: IRun) => {
                return item.latest_job_submission?.job_provisioning_data?.price
                    ? `$${item.latest_job_submission?.job_provisioning_data?.price}`
                    : null;
            },
        },
        {
            id: 'instance',
            header: `${t('projects.run.instance')}`,
            cell: (item: IRun) => item.latest_job_submission?.job_provisioning_data?.instance_type?.name,
        },
        {
            id: 'instance',
            header: `${t('projects.run.instance')}`,
            cell: (item: IRun) => item.latest_job_submission?.job_provisioning_data?.instance_type?.name,
        },
        {
            id: 'region',
            header: `${t('projects.run.region')}`,
            cell: (item: IRun) => item.latest_job_submission?.job_provisioning_data?.region,
        },
        {
            id: 'backend',
            header: `${t('projects.run.backend')}`,
            cell: (item: IRun) => item.latest_job_submission?.job_provisioning_data?.backend,
        },
    ];

    return { columns } as const;
};
