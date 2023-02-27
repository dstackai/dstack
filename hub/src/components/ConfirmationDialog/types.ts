import { ReactNode } from 'react';

export interface IProps {
    title?: string;
    content?: ReactNode;
    visible?: boolean;
    onDiscard?: () => void;
    onConfirm?: () => void;

    cancelButtonLabel?: string;
    confirmButtonLabel?: string;
}
