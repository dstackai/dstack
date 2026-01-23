import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@cloudscape-design/components/box';

import { Button } from '../Button';
import { ConfirmationDialog } from '../ConfirmationDialog';

import { IProps } from './types';

export const ButtonWithConfirmation: React.FC<IProps> = ({
    confirmTitle,
    confirmContent,
    onClick,
    confirmButtonLabel,
    ...props
}) => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const onConfirm = () => {
        if (onClick) onClick();

        setShowConfirmDelete(false);
    };

    const getContent = () => {
        if (!confirmContent) {
            return <Box variant="span">{t('confirm_dialog.message')}</Box>;
        }

        if (typeof confirmContent === 'string') {
            return <Box variant="span">{confirmContent}</Box>;
        }

        return confirmContent;
    };

    return (
        <>
            <Button {...props} onClick={toggleDeleteConfirm} />

            <ConfirmationDialog
                visible={showDeleteConfirm}
                onDiscard={toggleDeleteConfirm}
                onConfirm={onConfirm}
                title={confirmTitle}
                content={getContent()}
                confirmButtonLabel={confirmButtonLabel ?? t('common.delete')}
            />
        </>
    );
};
