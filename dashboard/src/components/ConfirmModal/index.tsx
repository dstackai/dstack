import React from 'react';
import { useTranslation } from 'react-i18next';
import Modal, { Props as ModalProps } from 'components/Modal';
import Button, { ButtonProps } from 'components/Button';

export interface Props extends ModalProps {
    ok: () => void;
    title: string;
    children?: React.ReactNode;
    confirmButtonProps?: Partial<ButtonProps>;
    cancelButtonProps?: Partial<ButtonProps>;
}

const ConfirmModal: React.FC<Props> = ({ ok, title, children, confirmButtonProps, cancelButtonProps = {}, ...props }) => {
    const { t } = useTranslation();

    return (
        <Modal {...props}>
            <Modal.Title>{title}</Modal.Title>

            <Modal.Content>{children}</Modal.Content>

            <Modal.Buttons>
                <Button appearance="blue-fill" onClick={ok} {...confirmButtonProps}>
                    {confirmButtonProps?.children || t('ok')}
                </Button>

                <Button appearance="gray-stroke" onClick={props.close} {...cancelButtonProps}>
                    {cancelButtonProps?.children || t('cancel')}
                </Button>
            </Modal.Buttons>
        </Modal>
    );
};

export default ConfirmModal;
