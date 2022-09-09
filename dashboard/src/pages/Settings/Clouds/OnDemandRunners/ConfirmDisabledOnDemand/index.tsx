import React from 'react';
import { useTranslation } from 'react-i18next';
import Modal, { Props as ModalProps } from 'components/Modal';
import Button from 'components/Button';

export interface Props extends ModalProps {
    ok: () => void;
}

const ConfirmStopRun: React.FC<Props> = ({ close, ok, ...props }) => {
    const { t } = useTranslation();

    return (
        <Modal close={close} {...props}>
            <Modal.Title>{t('Disable on-demand runners')}</Modal.Title>

            <Modal.Content>
                {t('Are you sure you want to disabled on-demand runners? The change will take effect immediately.')}
            </Modal.Content>

            <Modal.Buttons>
                <Button appearance="red-stroke" onClick={ok}>
                    {t('yes_disable')}
                </Button>

                <Button appearance="gray-stroke" onClick={close}>
                    {t('cancel')}
                </Button>
            </Modal.Buttons>
        </Modal>
    );
};

export default ConfirmStopRun;
