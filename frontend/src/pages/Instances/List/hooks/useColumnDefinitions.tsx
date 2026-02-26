import React from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { Icon, NavigateLink, StatusIndicator, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { formatBackend, getStatusIconType } from 'libs/fleet';
import { formatInstanceStatusText, getHealthStatusIconType, prettyEnumValue } from 'libs/instance';
import { formatResources } from 'libs/resources';
import { ROUTES } from 'routes';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<IInstance>[] = [
        {
            id: 'name',
            header: t('fleets.instances.instance_name'),
            cell: (item) =>
                item.project_name ? (
                    <NavigateLink href={ROUTES.INSTANCES.DETAILS.FORMAT(item.project_name, item.id)}>{item.name}</NavigateLink>
                ) : (
                    item.name
                ),
        },
        {
            id: 'fleet_name',
            header: t('fleets.fleet'),
            cell: (item) =>
                item.fleet_name && item.project_name ? (
                    <NavigateLink href={ROUTES.FLEETS.DETAILS.FORMAT(item.project_name, item.fleet_id)}>
                        {item.fleet_name}
                    </NavigateLink>
                ) : (
                    '-'
                ),
        },
        {
            id: 'project_name',
            header: t('fleets.instances.project'),
            cell: (item) =>
                item.project_name ? (
                    <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(item.project_name)}>{item.project_name}</NavigateLink>
                ) : (
                    item.project_name
                ),
        },
        {
            id: 'status',
            header: t('fleets.instances.status'),
            cell: (item) => (
                <StatusIndicator type={getStatusIconType(item.status)}>{formatInstanceStatusText(item)}</StatusIndicator>
            ),
        },
        {
            id: 'error',
            header: t('projects.run.error'),
            cell: (item) => {
                if (item.unreachable) return <StatusIndicator type="error">Unreachable</StatusIndicator>;
                if (item.health_status !== 'healthy')
                    return (
                        <StatusIndicator type={getHealthStatusIconType(item.health_status)}>
                            {prettyEnumValue(item.health_status)}
                        </StatusIndicator>
                    );
                return null;
            },
        },
        {
            id: 'hostname',
            header: t('fleets.instances.hostname'),
            cell: (item) => item.hostname,
        },
        {
            id: 'backend',
            header: t('fleets.instances.backend'),
            cell: (item) => formatBackend(item.backend),
        },
        {
            id: 'price',
            header: t('fleets.instances.price'),
            cell: (item) => (typeof item.price === 'number' ? `$${item.price}` : '-'),
        },
        {
            id: 'region',
            header: t('fleets.instances.region'),
            cell: (item) => item.region,
        },
        {
            id: 'instance_type',
            header: t('fleets.instances.instance_type'),
            cell: (item) => item.instance_type?.name ?? '-',
        },
        {
            id: 'resources',
            header: t('fleets.instances.resources'),
            cell: (item) => (item.instance_type ? formatResources(item.instance_type.resources) : '-'),
        },
        {
            id: 'spot',
            header: t('fleets.instances.spot'),
            cell: (item) => item.instance_type?.resources.spot && <Icon name={'check'} />,
        },
        {
            id: 'started',
            header: t('fleets.instances.started'),
            cell: (item) => format(new Date(item.created), DATE_TIME_FORMAT),
        },
        {
            id: 'finished_at',
            header: t('fleets.instances.finished_at'),
            cell: (item) => (item.finished_at ? format(new Date(item.finished_at), DATE_TIME_FORMAT) : '-'),
        },
    ];

    return { columns } as const;
};
