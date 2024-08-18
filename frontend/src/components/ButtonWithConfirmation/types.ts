import { ReactNode } from 'react';

import type { IProps as ButtonProps } from '../Button';

export interface IProps extends Omit<ButtonProps, 'onClick'> {
    confirmTitle?: string;
    confirmContent?: ReactNode;
    onClick?: () => void;
}
