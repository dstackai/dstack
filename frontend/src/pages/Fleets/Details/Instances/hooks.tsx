import React from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { Icon, StatusIndicator, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { getStatusIconType } from 'libs/fleet';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<IInstance>[] = [
        {
            id: 'instance_name',
            header: t('pools.instances.instance_name'),
            cell: (item) => item.name,
        },
        {
            id: 'status',
            header: t('pools.instances.status'),
            cell: (item) => (
                <StatusIndicator type={getStatusIconType(item.status)}>
                    {t(`pools.instances.statuses.${item.status}`)}
                </StatusIndicator>
            ),
        },
        {
            id: 'resources',
            header: t('pools.instances.resources'),
            cell: (item) => item.instance_type.resources.description,
        },
        {
            id: 'backend',
            header: t('pools.instances.backend'),
            cell: (item) => item.backend,
        },
        {
            id: 'region',
            header: t('pools.instances.region'),
            cell: (item) => item.region,
        },
        {
            id: 'spot',
            header: t('pools.instances.spot'),
            cell: (item) => item.instance_type.resources.spot && <Icon name={'check'} />,
        },
        {
            id: 'started',
            header: t('pools.instances.started'),
            cell: (item) => format(new Date(item.created), DATE_TIME_FORMAT),
        },
        {
            id: 'price',
            header: t('pools.instances.price'),
            cell: (item) => item.price && `$${item.price}`,
        },
    ];

    return { columns } as const;
};
