import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from 'components';
import { ButtonWithConfirmation } from 'components/ButtonWithConfirmation';

import styles from '../styles.module.scss';

type hookArgs = {
    loading?: boolean;
    onDeleteClick?: (backend: IProjectBackend) => void;
    onEditClick?: (backend: IProjectBackend) => void;
};

export const useColumnsDefinitions = ({ loading, onDeleteClick, onEditClick }: hookArgs) => {
    const { t } = useTranslation();

    const columns = useMemo(() => {
        return [
            {
                id: 'type',
                header: t('projects.edit.backend_type'),
                cell: (backend: IProjectBackend) => backend.config.type,
            },

            {
                id: 'actions',
                header: '',

                cell: (backend: IProjectBackend) =>
                    backend.config.type !== 'dstack' && (
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
