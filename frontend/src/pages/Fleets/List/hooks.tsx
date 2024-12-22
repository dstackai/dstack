import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { Button, Icon, ListEmptyMessage, StatusIndicator, TableProps } from 'components';
import { SelectCSDProps } from 'components';

import { DATE_TIME_FORMAT, DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { getFleetStatusIconType } from 'libs/fleet';
import { useLazyGetFleetsQuery } from 'services/fleet';
import { useGetProjectsQuery } from 'services/project';

export const useEmptyMessages = ({
    clearFilters,
    isDisabledClearFilter,
}: {
    clearFilters?: () => void;
    isDisabledClearFilter?: boolean;
}) => {
    const { t } = useTranslation();

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('fleets.empty_message_title')} message={t('fleets.empty_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilters}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilters, isDisabledClearFilter]);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('fleets.nomatch_message_title')} message={t('fleets.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilters}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilters, isDisabledClearFilter]);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<IFleet>[] = [
        {
            id: 'instance_name',
            header: t('fleets.instances.instance_name'),
            cell: (item) => item.name,
        },
        {
            id: 'status',
            header: t('fleets.instances.status'),
            cell: (item) => (
                <StatusIndicator type={getFleetStatusIconType(item.status)}>
                    {t(`fleets.statuses.${item.status}`)}
                </StatusIndicator>
            ),
        },
        {
            id: 'project',
            header: t('fleets.instances.project'),
            cell: (item) => item.project_name,
        },
        // {
        //     id: 'resources',
        //     header: t('fleets.instances.resources'),
        //     cell: (item) => item.instance_type?.resources.description,
        // },
        {
            id: 'backend',
            header: t('fleets.instances.backend'),
            cell: (item) => item.spec.configuration?.backends?.join(', '),
        },
        {
            id: 'region',
            header: t('fleets.instances.region'),
            cell: (item) => item.spec.configuration.regions?.join(', '),
        },
        {
            id: 'spot',
            header: t('fleets.instances.spot'),
            cell: (item) => item.spec.configuration?.spot_policy === 'spot' && <Icon name={'check'} />,
        },
        {
            id: 'started',
            header: t('fleets.instances.started'),
            cell: (item) => format(new Date(item.created_at), DATE_TIME_FORMAT),
        },
        {
            id: 'price',
            header: t('fleets.instances.price'),
            cell: (item) => item.spec.configuration?.max_price && `$${item.spec.configuration?.max_price}`,
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

    const isDisabledClearFilter = !selectedProject && !onlyActive;

    return {
        projectOptions,
        selectedProject,
        setSelectedProject,
        onlyActive,
        setOnlyActive,
        clearFilters,
        isDisabledClearFilter,
    } as const;
};

export const useFleetsData = ({ project_name, only_active }: TFleetListRequestParams) => {
    const [data, setData] = useState<IFleet[]>([]);
    const [pagesCount, setPagesCount] = useState<number>(1);
    const [disabledNext, setDisabledNext] = useState(false);
    const lastRequestParams = useRef<TFleetListRequestParams | undefined>(undefined);

    const [getFleets, { isLoading, isFetching }] = useLazyGetFleetsQuery();

    const getFleetsRequest = (params?: TFleetListRequestParams) => {
        lastRequestParams.current = params;
        return getFleets({
            project_name,
            only_active,
            limit: DEFAULT_TABLE_PAGE_SIZE,
            ...params,
        }).unwrap();
    };

    const refreshList = () => {
        getFleetsRequest(lastRequestParams.current).then((result) => {
            setDisabledNext(false);
            setData(result);
        });
    };

    useEffect(() => {
        getFleetsRequest().then((result) => {
            setPagesCount(1);
            setDisabledNext(false);
            setData(result);
        });
    }, [project_name, only_active]);

    const nextPage = async () => {
        if (data.length === 0 || disabledNext) {
            return;
        }

        try {
            const result = await getFleetsRequest({
                prev_created_at: data[data.length - 1].created_at,
                prev_id: data[data.length - 1].id,
            });

            if (result.length > 0) {
                setPagesCount((count) => count + 1);
                setData(result);
            } else {
                setDisabledNext(true);
            }
        } catch (e) {
            console.log(e);
        }
    };

    const prevPage = async () => {
        if (pagesCount === 1) {
            return;
        }

        try {
            const result = await getFleetsRequest({
                prev_created_at: data[0].created_at,
                prev_id: data[0].id,
                ascending: true,
            });

            setDisabledNext(false);

            if (result.length > 0) {
                setPagesCount((count) => count - 1);
                setData(result);
            } else {
                setPagesCount(1);
            }
        } catch (e) {
            console.log(e);
        }
    };

    return { data, pagesCount, disabledNext, isLoading: isLoading || isFetching, nextPage, prevPage, refreshList };
};
