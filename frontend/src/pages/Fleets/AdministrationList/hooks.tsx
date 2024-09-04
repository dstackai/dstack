import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { Icon, StatusIndicator, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { getStatusIconType } from 'libs/fleet';

import { SelectCSDProps } from '../../../components';
import { useLocalStorageState } from '../../../hooks/useLocalStorageState';
import { useGetProjectsQuery } from '../../../services/project';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<IInstanceListItem>[] = [
        {
            id: 'instance_name',
            header: t('fleets.instances.instance_name'),
            cell: (item) => item.name,
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
            id: 'project',
            header: t('fleets.instances.project'),
            cell: (item) => item.project_name,
        },
        {
            id: 'resources',
            header: t('fleets.instances.resources'),
            cell: (item) => item.instance_type?.resources.description,
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
            id: 'price',
            header: t('fleets.instances.price'),
            cell: (item) => item.price && `$${item.price}`,
        },
    ];

    return { columns } as const;
};

export const useFilters = () => {
    const [onlyActive, setOnlyActive] = useLocalStorageState<boolean>('administration-fleet-list-is-active', false);
    const [selectedProject, setSelectedProject] = useState<SelectCSDProps.Option | null>(null);

    const { data: projectsData } = useGetProjectsQuery();

    const projectOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!projectsData?.length) return [];

        return projectsData.map((project) => ({ label: project.project_name, value: project.project_name }));
    }, [projectsData]);

    const clearFilters = () => {
        setOnlyActive(false);
        setSelectedProject(null);
    };

    const filteringFunction = useCallback<(pool: IPoolListItem) => boolean>(
        (pool: IPoolListItem) => {
            return !(onlyActive && pool.total_instances === 0);
        },
        [onlyActive],
    );

    const isDisabledClearFilter = !selectedProject && !onlyActive;

    return {
        projectOptions,
        selectedProject,
        setSelectedProject,
        onlyActive,
        setOnlyActive,
        filteringFunction,
        clearFilters,
        isDisabledClearFilter,
    } as const;
};
