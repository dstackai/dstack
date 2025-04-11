import React from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { NavigateLink, StatusIndicator } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { getRepoNameFromRun, getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';

import {
    getRunListItemBackend,
    getRunListItemInstance,
    getRunListItemPrice,
    getRunListItemRegion,
    getRunListItemResources,
    getRunListItemSpotLabelKey,
} from '../helpers';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns = [
        {
            id: 'run_name',
            header: t('projects.run.run_name'),
            cell: (item: IRun) => {
                return item.id !== null ? (
                    <NavigateLink href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(item.project_name, item.id)}>
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
            cell: (item: IRun) => (
                <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(item.project_name)}>{item.project_name}</NavigateLink>
            ),
        },
        {
            id: 'repo',
            header: `${t('projects.run.repo')}`,
            cell: (item: IRun) => getRepoNameFromRun(item),
        },
        {
            id: 'hub_user_name',
            header: `${t('projects.run.hub_user_name')}`,
            cell: (item: IRun) => <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(item.user)}>{item.user}</NavigateLink>,
        },
        {
            id: 'submitted_at',
            header: t('projects.run.submitted_at'),
            cell: (item: IRun) => format(new Date(item.submitted_at), DATE_TIME_FORMAT),
        },
        {
            id: 'finished_at',
            header: t('projects.run.finished_at'),
            cell: (item: IRun) => (item.terminated_at ? format(new Date(item.terminated_at), DATE_TIME_FORMAT) : null),
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
            id: 'error',
            header: t('projects.run.error'),
            cell: (item: IRun) => item.error ?? '-',
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
            cell: getRunListItemResources,
        },
        {
            id: 'spot',
            header: `${t('projects.run.spot')}`,
            cell: (item: IRun) => t(getRunListItemSpotLabelKey(item)),
        },
        {
            id: 'price',
            header: `${t('projects.run.price')}`,
            cell: getRunListItemPrice,
        },
        {
            id: 'instance',
            header: `${t('projects.run.instance')}`,
            cell: getRunListItemInstance,
        },
        {
            id: 'region',
            header: `${t('projects.run.region')}`,
            cell: getRunListItemRegion,
        },
        {
            id: 'backend',
            header: `${t('projects.run.backend')}`,
            cell: getRunListItemBackend,
        },
    ];

    return { columns } as const;
};
