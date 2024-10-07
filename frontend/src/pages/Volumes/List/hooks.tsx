import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { Button, ListEmptyMessage, StatusIndicator } from 'components';
import { SelectCSDProps } from 'components';

import { DATE_TIME_FORMAT, DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { getStatusIconType } from 'libs/volumes';
import { useGetProjectsQuery } from 'services/project';
import { useLazyGetAllVolumesQuery } from 'services/volume';

export const useVolumesTableEmptyMessages = () => {
    const { t } = useTranslation();

    const renderEmptyMessage = (): React.ReactNode => {
        return <ListEmptyMessage title={t('volume.empty_message_title')} message={t('volume.empty_message_text')} />;
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('volume.nomatch_message_title')} message={t('volume.nomatch_message_text')}>
                <Button onClick={onClearFilter}>{t('common.clearFilter')}</Button>
            </ListEmptyMessage>
        );
    };

    return { renderEmptyMessage, renderNoMatchMessage };
};

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns = [
        {
            id: 'name',
            header: t('volume.name'),
            cell: (item: IVolume) => item.name,
        },
        {
            id: 'backend',
            header: `${t('volume.backend')}`,
            cell: (item: IVolume) => item.configuration?.backend ?? '-',
        },
        {
            id: 'region',
            header: `${t('volume.region')}`,
            cell: (item: IVolume) => item.configuration?.backend ?? '-',
        },

        {
            id: 'status',
            header: t('volume.status'),
            cell: (item: IVolume) =>
                item.deleted ? (
                    <StatusIndicator type="error">{t(`volume.statuses.deleted`)}</StatusIndicator>
                ) : (
                    <StatusIndicator type={getStatusIconType(item.status)}>
                        {t(`volume.statuses.${item.status}`)}
                    </StatusIndicator>
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
                return item?.provisioning_data?.price ? `$${item.provisioning_data.price.toFixed(2)}` : '-';
            },
        },
    ];

    return { columns } as const;
};

export const useVolumesData = ({ project_name, only_active }: TVolumesListRequestParams) => {
    const [data, setData] = useState<IVolume[]>([]);
    const [pagesCount, setPagesCount] = useState<number>(1);
    const [disabledNext, setDisabledNext] = useState(false);

    const [getVolumes, { isLoading, isFetching }] = useLazyGetAllVolumesQuery();

    const getVolumesRequest = (params?: TVolumesListRequestParams) => {
        return getVolumes({
            project_name,
            only_active,
            limit: DEFAULT_TABLE_PAGE_SIZE,
            ...params,
        })
            .unwrap()
            .then((result) => {
                return result;
            });
    };

    useEffect(() => {
        getVolumesRequest().then((result) => {
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
            const result = await getVolumesRequest({
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
            const result = await getVolumesRequest({
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

    return { data, pagesCount, disabledNext, isLoading: isLoading || isFetching, nextPage, prevPage };
};

export const useFilters = (storagePrefix?: string) => {
    const [onlyActive, setOnlyActive] = useLocalStorageState<boolean>(`${storagePrefix}volume-list-is-active`, false);
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
