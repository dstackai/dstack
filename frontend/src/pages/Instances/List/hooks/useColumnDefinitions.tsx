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
            id: 'fleet_name',
            header: t('fleets.fleet'),
            cell: (item) => item.fleet_name ?? '-',
        },
        {
            id: 'instance_num',
            header: t('fleets.instances.instance_num'),
            cell: (item) => item.instance_num,
        },
        {
            id: 'project_name',
            header: t('fleets.instances.project'),
            cell: (item) => item.project_name,
        },
        {
            id: 'hostname',
            header: t('fleets.instances.hostname'),
            cell: (item) => item.hostname,
        },
        {
            id: 'backend',
            header: t('fleets.instances.backend'),
            cell: (item) => item.backend,
        },
        {
            id: 'region',
            header: t('fleets.instances.region'),
            cell: (item) => item.region,
        },
        {
            id: 'instance_type',
            header: t('fleets.instances.instance_type'),
            cell: (item) => item.instance_type.name,
        },
        {
            id: 'resources',
            header: t('fleets.instances.resources'),
            cell: (item) => item.instance_type.resources.description,
        },
        {
            id: 'spot',
            header: t('fleets.instances.spot'),
            cell: (item) => item.instance_type.resources.spot && <Icon name={'check'} />,
        },
        {
            id: 'status',
            header: t('fleets.instances.status'),
            cell: (item) => (
                <StatusIndicator type={getStatusIconType(item.status)}>
                    {t(`fleets.instances.statuses.${item.status}`)}
                </StatusIndicator>
            ),
        },
        {
            id: 'started',
            header: t('fleets.instances.started'),
            cell: (item) => format(new Date(item.created), DATE_TIME_FORMAT),
        },
        {
            id: 'price',
            header: t('fleets.instances.price'),
            cell: (item) => item.price && `$${item.price}`,
        },
    ];

    return { columns } as const;
};
