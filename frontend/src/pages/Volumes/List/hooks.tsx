import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { Button, ListEmptyMessage, NavigateLink, StatusIndicator } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useNotifications } from 'hooks';
import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { useProjectFilter } from 'hooks/useProjectFilter';
import { getServerError } from 'libs';
import { getStatusIconType } from 'libs/volumes';
import { ROUTES } from 'routes';
import { useDeleteVolumesMutation } from 'services/volume';

export const useVolumesTableEmptyMessages = ({
    clearFilters,
    isDisabledClearFilter,
}: {
    clearFilters?: () => void;
    isDisabledClearFilter?: boolean;
}) => {
    const { t } = useTranslation();

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('volume.empty_message_title')} message={t('volume.empty_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilters}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    };

    const renderNoMatchMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('volume.nomatch_message_title')} message={t('volume.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilters}>
                    {t('common.clearFilter')}
                </Button>
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
            id: 'project',
            header: `${t('volume.project')}`,
            cell: (item: IVolume) => (
                <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(item.project_name)}>{item.project_name}</NavigateLink>
            ),
        },
        {
            id: 'backend',
            header: `${t('volume.backend')}`,
            cell: (item: IVolume) => item.configuration?.backend ?? '-',
        },
        {
            id: 'region',
            header: `${t('volume.region')}`,
            cell: (item: IVolume) => item.configuration?.region ?? '-',
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
            id: 'created',
            header: t('volume.created'),
            cell: (item: IVolume) => format(new Date(item.created_at), DATE_TIME_FORMAT),
        },
        {
            id: 'finished',
            header: t('volume.finished'),
            cell: (item: IVolume) => getVolumeFinised(item),
        },
        {
            id: 'price',
            header: `${t('volume.price')}`,
            cell: (item: IVolume) => {
                return item?.provisioning_data?.price ? `$${item.provisioning_data.price.toFixed(2)}` : '-';
            },
        },
        {
            id: 'cost',
            header: `${t('volume.cost')}`,
            cell: (item: IVolume) => {
                return item?.cost ? `$${item.cost.toFixed(2)}` : '-';
            },
        },
    ];

    return { columns } as const;
};

export const useFilters = (localStorePrefix = 'volume-list-page') => {
    const [onlyActive, setOnlyActive] = useLocalStorageState<boolean>(`${localStorePrefix}-is-active`, true);
    const { selectedProject, setSelectedProject, projectOptions } = useProjectFilter({ localStorePrefix });

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

export const useVolumesDelete = () => {
    const { t } = useTranslation();
    const [deleteVolumesRequest] = useDeleteVolumesMutation();
    const [pushNotification] = useNotifications();
    const [isDeleting, setIsDeleting] = useState(() => false);

    const namesOfVolumesGroupByProjectName = (volumes: IVolume[]) => {
        return volumes.reduce<Record<string, string[]>>((acc, volume) => {
            if (acc[volume.project_name]) {
                acc[volume.project_name].push(volume.name);
            } else {
                acc[volume.project_name] = [volume.name];
            }

            return acc;
        }, {});
    };

    const deleteVolumes = (volumes: IVolume[]) => {
        if (!volumes.length) return Promise.reject('No volumes');

        setIsDeleting(true);

        const groupedVolumes = namesOfVolumesGroupByProjectName(volumes);

        const requests = Object.keys(groupedVolumes).map((projectName) => {
            return deleteVolumesRequest({
                project_name: projectName,
                names: groupedVolumes[projectName],
            }).unwrap();
        });

        return Promise.all(requests)
            .finally(() => setIsDeleting(false))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    };

    return { isDeleting, deleteVolumes };
};

const getVolumeFinised = (volume: IVolume): string => {
    if (!volume.deleted_at && volume.status != 'failed') {
        return '-';
    }
    let finished = volume.last_processed_at
    if (volume.deleted_at) {
        finished = volume.deleted_at
    }
    return format(new Date(finished), DATE_TIME_FORMAT);
};
