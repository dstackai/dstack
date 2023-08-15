import { ReactNode } from 'react';
import type { ButtonProps } from '@cloudscape-design/components/button';

export interface IProps extends Omit<ButtonProps, 'onClick'> {
    confirmTitle?: string;
    confirmContent?: ReactNode;
    onClick?: () => void;
}
