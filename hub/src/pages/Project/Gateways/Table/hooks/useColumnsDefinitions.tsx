import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from 'components';
import { ButtonWithConfirmation } from 'components/ButtonWithConfirmation';

import styles from '../styles.module.scss';

type hookArgs = {
    loading?: boolean;
    onDeleteClick?: (gateway: IGateway) => void;
    onEditClick?: (gateway: IGateway) => void;
};

export const useColumnsDefinitions = ({ loading, onDeleteClick, onEditClick }: hookArgs) => {
    const { t } = useTranslation();

    const columns = useMemo(() => {
        return [
            {
                id: 'type',
                header: t('gateway.table.backend'),
                cell: (gateway: IGateway) => gateway.backend,
            },

            {
                id: 'bucket',
                header: t('gateway.table.region'),

                cell: (gateway: IGateway) => (
                    <div className={styles.cell}>
                        <div>{gateway.head.region}</div>

                        <div className={styles.contextMenu}>
                            {onEditClick && (
                                <Button
                                    disabled={loading}
                                    formAction="none"
                                    onClick={() => onEditClick(gateway)}
                                    variant="icon"
                                    iconName="edit"
                                />
                            )}

                            {onDeleteClick && (
                                <ButtonWithConfirmation
                                    disabled={loading}
                                    formAction="none"
                                    onClick={() => onDeleteClick(gateway)}
                                    variant="icon"
                                    iconName="remove"
                                    confirmTitle={t('gateway.edit.delete_gateway_confirm_title')}
                                    confirmContent={t('gateway.edit.delete_gateway_confirm_message')}
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
