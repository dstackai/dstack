import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from 'components';
import { ButtonWithConfirmation } from 'components/ButtonWithConfirmation';

import { BackendTypesEnum } from '../../Form/types';

import styles from '../styles.module.scss';

type hookArgs = {
    loading?: boolean;
    onDeleteClick?: (backend: IProjectBackend) => void;
    onEditClick?: (backend: IProjectBackend) => void;
};

export const useColumnsDefinitions = ({ loading, onDeleteClick, onEditClick }: hookArgs) => {
    const { t } = useTranslation();

    const getRegionByBackendType = (backend: IProjectBackend) => {
        switch (backend.config.type) {
            case BackendTypesEnum.AWS:
                return backend.config.region_name_title;
            case BackendTypesEnum.AZURE:
                return backend.config.location;
            case BackendTypesEnum.GCP:
                return backend.config.region;
            case BackendTypesEnum.LAMBDA: {
                const regions = backend.config?.regions.join(', ') ?? '-';
                return (
                    <div className={styles.ellipsisCell} title={regions}>
                        {regions}
                    </div>
                );
            }
            default:
                return '-';
        }
    };

    const getBucketByBackendType = (backend: IProjectBackend) => {
        switch (backend.config.type) {
            case BackendTypesEnum.AWS:
                return backend.config.s3_bucket_name;
            case BackendTypesEnum.GCP:
                return backend.config.bucket_name;
            case BackendTypesEnum.LAMBDA:
                return backend.config.storage_backend.bucket_name;
            default:
                return '-';
        }
    };

    const getSubnetByBackendType = (backend: IProjectBackend) => {
        switch (backend.config.type) {
            case BackendTypesEnum.AWS:
                return backend.config.ec2_subnet_id;
            case BackendTypesEnum.GCP:
                return backend.config.subnet;
            default:
                return '-';
        }
    };

    const getExtraRegionsByBackendType = (backend: IProjectBackend) => {
        switch (backend.config.type) {
            case BackendTypesEnum.AWS: {
                const extraRegions = backend.config.extra_regions?.join(', ');

                return (
                    <div className={styles.ellipsisCell} title={extraRegions}>
                        {extraRegions}
                    </div>
                );
            }

            case BackendTypesEnum.AZURE: {
                const extraLocations = backend.config.extra_locations?.join(', ');

                return (
                    <div className={styles.ellipsisCell} title={extraLocations}>
                        {extraLocations}
                    </div>
                );
            }

            case BackendTypesEnum.GCP: {
                const extraRegions = backend.config.extra_regions?.join(', ');

                return (
                    <div className={styles.ellipsisCell} title={extraRegions}>
                        {extraRegions}
                    </div>
                );
            }

            default:
                return '-';
        }
    };

    const columns = useMemo(() => {
        return [
            {
                id: 'type',
                header: t('projects.edit.backend_type'),
                cell: (backend: IProjectBackend) => backend.config.type,
            },

            {
                id: 'regions',
                header: t('backend.table.region'),
                cell: getRegionByBackendType,
            },

            {
                id: 'bucket',
                header: t('backend.table.bucket'),
                cell: getBucketByBackendType,
            },

            {
                id: 'subnet',
                header: t('backend.table.subnet'),
                cell: getSubnetByBackendType,
            },

            {
                id: 'extra_regions',
                header: t('backend.table.extra_regions'),
                cell: getExtraRegionsByBackendType,
            },

            {
                id: 'actions',
                header: '',
                cell: (backend: IProjectBackend) => (
                    <div className={styles.cell}>
                        <div className={styles.contextMenu}>
                            {onEditClick && (
                                <Button
                                    disabled={loading}
                                    formAction="none"
                                    onClick={() => onEditClick(backend)}
                                    variant="icon"
                                    iconName="edit"
                                />
                            )}

                            {onDeleteClick && (
                                <ButtonWithConfirmation
                                    disabled={loading}
                                    formAction="none"
                                    onClick={() => onDeleteClick(backend)}
                                    variant="icon"
                                    iconName="remove"
                                    confirmTitle={t('backend.edit.delete_backend_confirm_title')}
                                    confirmContent={t('backend.edit.delete_backend_confirm_message')}
                                />
                            )}
                        </div>
                    </div>
                ),
            },
        ];
    }, [loading, onEditClick, onDeleteClick]);

    return { columns } as const;
};
