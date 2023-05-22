import React from 'react';

export interface IProps {
    title: React.ReactNode;
    editAction?: () => void;
    deleteAction?: () => void;
    editDisabled?: boolean;
    deleteDisabled?: boolean;
    actionButtons?: React.ReactNode;
}
