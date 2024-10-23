import React from 'react';
import { useTranslation } from 'react-i18next';

import { NavigateLink } from 'components';

import { ROUTES } from 'routes';

import {
    getJobListItemBackend,
    getJobListItemInstance,
    getJobListItemPrice,
    getJobListItemRegion,
    getJobListItemResources,
    getJobListItemSpot,
} from './helpers';

export const useColumnsDefinitions = ({ projectName, runName }: { projectName: string; runName: string }) => {
    const { t } = useTranslation();

    const columns = [
        {
            id: 'job_name',
            header: t('projects.run.job_name'),
            cell: (item: IJob) => (
                <NavigateLink
                    href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.FORMAT(projectName, runName, item.job_spec.job_name)}
                >
                    {item.job_spec.job_name}
                </NavigateLink>
            ),
        },
        {
            id: 'resources',
            header: `${t('projects.run.resources')}`,
            cell: getJobListItemResources,
        },
        {
            id: 'spot',
            header: `${t('projects.run.spot')}`,
            cell: getJobListItemSpot,
        },
        {
            id: 'price',
            header: `${t('projects.run.price')}`,
            cell: getJobListItemPrice,
        },
        {
            id: 'instance',
            header: `${t('projects.run.instance')}`,
            cell: getJobListItemInstance,
        },
        {
            id: 'region',
            header: `${t('projects.run.region')}`,
            cell: getJobListItemRegion,
        },
        {
            id: 'backend',
            header: `${t('projects.run.backend')}`,
            cell: getJobListItemBackend,
        },
    ];

    return { columns } as const;
};
