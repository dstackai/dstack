import React from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { StatusIndicator } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { getStatusIconType } from 'libs/volumes';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns = [
        {
            id: 'name',
            header: t('volume.name'),
            cell: (item: IVolume) => item.name,
        },
        {
            id: 'project',
            header: `${t('volume.project')}`,
            cell: (item: IVolume) => item.project_name,
        },
        {
            id: 'backend',
            header: `${t('volume.backend')}`,
            cell: (item: IVolume) => item.configuration.backend,
        },
        {
            id: 'region',
            header: `${t('volume.region')}`,
            cell: (item: IVolume) => item.configuration.backend,
        },

        {
            id: 'status',
            header: t('volume.status'),
            cell: (item: IVolume) => (
                <StatusIndicator type={getStatusIconType(item.status)}>{t(`volume.statuses.${item.status}`)}</StatusIndicator>
            ),
        },
        {
            id: 'created_at',
            header: t('volume.created_at'),
            cell: (item: IVolume) => format(new Date(item.created_at), DATE_TIME_FORMAT),
        },
        {
            id: 'price',
            header: `${t('volume.price')}`,
            cell: (item: IVolume) => {
                return `$${item.provisioning_data.price}`;
            },
        },
    ];

    return { columns } as const;
};
