import React from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import Modal from '@cloudscape-design/components/modal';
import SpaceBetween from '@cloudscape-design/components/space-between';

import { IProps } from './types';

export const ConfirmationDialog: React.FC<IProps> = ({
    title: titleProp,
    content: contentProp,
    visible = false,
    onDiscard,
    onConfirm,
    cancelButtonLabel: cancelButtonLabelProp,
    confirmButtonLabel: confirmButtonLabelProp,
}) => {
    const { t } = useTranslation();
    const title = titleProp ?? t('confirm_dialog.title');
    const content = contentProp ?? <Box variant="span">{t('confirm_dialog.message')}</Box>;
    const cancelButtonLabel = cancelButtonLabelProp ?? t('common.cancel');
    const confirmButtonLabel = confirmButtonLabelProp ?? t('common.delete');

    return (
        <Modal
            visible={visible}
            onDismiss={onDiscard}
            header={title}
            footer={
                <Box float="right">
                    <SpaceBetween direction="horizontal" size="xs">
                        <Button variant="link" onClick={onDiscard}>
                            {cancelButtonLabel}
                        </Button>

                        <Button variant="primary" onClick={onConfirm}>
                            {confirmButtonLabel}
                        </Button>
                    </SpaceBetween>
                </Box>
            }
        >
            {content}
        </Modal>
    );
};
