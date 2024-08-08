import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Icon } from 'components';
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
                header: t('gateway.edit.backend'),
                cell: (gateway: IGateway) => gateway.backend,
            },

            {
                id: 'region',
                header: t('gateway.edit.region'),
                cell: (gateway: IGateway) => gateway.region,
            },

            {
                id: 'default',
                header: t('gateway.edit.default'),
                cell: (gateway: IGateway) => gateway.default && <Icon name={'check'} />,
            },

            {
                id: 'external_ip',
                header: t('gateway.edit.external_ip'),
                cell: (gateway: IGateway) => gateway.ip_address,
            },

            {
                id: 'wildcard_domain',
                header: t('gateway.edit.wildcard_domain'),

                cell: (gateway: IGateway) => (
                    <div className={styles.cell}>
                        <div>{gateway.wildcard_domain}</div>

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
