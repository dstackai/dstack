import React from 'react';
import { useTranslation } from 'react-i18next';
import Modal, { Props as ModalProps } from 'components/Modal';
import Button from 'components/Button';

export interface Props extends ModalProps {
    ok: () => void;
    totalCount: number;
    taggedCount?: number;
}

const ConfirmDeleteRun: React.FC<Props> = ({ close, ok, totalCount, taggedCount, ...props }) => {
    const { t } = useTranslation();

    return (
        <Modal close={close} {...props}>
            <Modal.Title>{t('delete_run', { count: totalCount })}</Modal.Title>

            <Modal.Content>
                {totalCount > 1 && taggedCount
                    ? t('confirm_message_remove_run_with_count_tagged_count', {
                          workflowCount: totalCount,
                          count: taggedCount,
                      })
                    : t('confirm_message_remove_run_with_count', {
                          count: totalCount,
                      })}
            </Modal.Content>

            <Modal.Buttons>
                <Button appearance="red-stroke" onClick={ok}>
                    {totalCount > 1 && taggedCount ? t('yes_delete_selected') : t('yes_delete')}
                </Button>

                <Button appearance="gray-stroke" onClick={close}>
                    {t('cancel')}
                </Button>
            </Modal.Buttons>
        </Modal>
    );
};

export default ConfirmDeleteRun;
