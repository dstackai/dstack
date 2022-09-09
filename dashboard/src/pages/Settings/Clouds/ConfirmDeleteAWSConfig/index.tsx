import React from 'react';
import { useTranslation } from 'react-i18next';
import ConfirmModal, { Props as ConfirmModalProps } from 'components/ConfirmModal';

export type Props = Omit<ConfirmModalProps, 'title' | 'confirmButtonProps'>;

const ConfirmStopRun: React.FC<Props> = ({ ...props }) => {
    const { t } = useTranslation();

    return (
        <ConfirmModal
            title={t('delete_settings')}
            confirmButtonProps={{ children: t('yes_delete'), appearance: 'red-stroke' }}
            {...props}
        >
            {t('confirm_messages.delete_aws')}
        </ConfirmModal>
    );
};

export default ConfirmStopRun;
