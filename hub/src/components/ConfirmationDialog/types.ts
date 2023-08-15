import { ReactNode } from 'react';

import { ButtonProps } from 'components';

export interface IProps {
    title?: string;
    content?: ReactNode;
    visible?: boolean;
    onDiscard: ButtonProps['onClick'];
    onConfirm: ButtonProps['onClick'];

    cancelButtonLabel?: string;
    confirmButtonLabel?: string;
}
