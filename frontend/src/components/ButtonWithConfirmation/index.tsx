import React, { useState } from 'react';
import Box from '@cloudscape-design/components/box';

import { Button } from '../Button';
import { ConfirmationDialog } from '../ConfirmationDialog';

import { IProps } from './types';

export const ButtonWithConfirmation: React.FC<IProps> = ({ confirmTitle, confirmContent, onClick, ...props }) => {
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const content = typeof confirmContent === 'string' ? <Box variant="span">{confirmContent}</Box> : confirmContent;

    const onConfirm = () => {
        if (onClick) onClick();

        setShowConfirmDelete(false);
    };

    return (
        <>
            <Button {...props} onClick={toggleDeleteConfirm} />

            <ConfirmationDialog
                visible={showDeleteConfirm}
                onDiscard={toggleDeleteConfirm}
                onConfirm={onConfirm}
                title={confirmTitle}
                content={content}
            />
        </>
    );
};
