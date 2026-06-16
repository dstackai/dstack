import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Icon } from 'components';
import { ButtonWithConfirmation } from 'components/ButtonWithConfirmation';

import styles from '../styles.module.scss';

type hookArgs = {
    loading?: boolean;
    projectName: string;
    onDeleteClick?: (gateway: IGateway) => void;
    onEditClick?: (gateway: IGateway) => void;
};

export const useColumnsDefinitions = ({ loading, projectName, onDeleteClick, onEditClick }: hookArgs) => {
    const { t } = useTranslation();

    const columns = useMemo(() => {
        return [
            {
                id: 'name',
                header: t('gateway.edit.name'),
                cell: (gateway: IGateway) =>
                    gateway.project_name && gateway.project_name !== projectName
                        ? `${gateway.project_name}/${gateway.name}`
                        : gateway.name,
            },

            {
                id: 'type',
                header: t('gateway.edit.backend'),
                cell: (gateway: IGateway) =>
                    gateway.replicas.length > 0 ? gateway.replicas.map((r, i) => <div key={i}>{r.backend}</div>) : null,
            },

            {
                id: 'region',
                header: t('gateway.edit.region'),
                cell: (gateway: IGateway) =>
                    gateway.replicas.length > 0 ? gateway.replicas.map((r, i) => <div key={i}>{r.region}</div>) : null,
            },

            {
                id: 'default',
                header: t('gateway.edit.default'),
                cell: (gateway: IGateway) => gateway.default && <Icon name={'check'} />,
            },

            {
                id: 'hostname',
                header: t('gateway.edit.hostname'),
                cell: (gateway: IGateway) => {
                    if (gateway.hostname) return gateway.hostname;
                    if (gateway.replicas.length > 0) return gateway.replicas.map((r, i) => <div key={i}>{r.hostname}</div>);
                    return null;
                },
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
    }, [loading, projectName, onEditClick, onDeleteClick]);

    return { columns } as const;
};
