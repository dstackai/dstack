import React from 'react';
import classNames from 'classnames';
import ButtonGeneral, { ButtonProps } from '@cloudscape-design/components/button';

import styles from './styles.module.scss';

type Variant = ButtonProps.Variant | 'danger-normal';

export interface IProps extends Omit<ButtonProps, 'variant'> {
    variant?: Variant;
}

export const Button: React.FC<IProps> = ({ children, variant, ...props }) => {
    const componentVariant: ButtonProps.Variant | undefined = variant === 'danger-normal' ? 'normal' : variant;
    return (
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        <ButtonGeneral {...props} className={classNames(styles.button, styles[variant], classNames)} variant={componentVariant}>
            {children}
        </ButtonGeneral>
    );
};
