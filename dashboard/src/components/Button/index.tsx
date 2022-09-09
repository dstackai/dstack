import React from 'react';
import cn from 'classnames';
import type { ButtonHTMLAttributes } from 'react';
import { ReactComponent as LoadingIcon } from 'assets/icons/loading.svg';
import css from './index.module.css';

export type ButtonDimension = 's' | 'xm' | 'm' | 'l' | 'xl' | 'xxl';
export type ButtonDirection = 'left' | 'right';

export type ButtonAppearance =
    | 'blue-transparent'
    | 'black-transparent'
    | 'black-fill'
    | 'black-stroke'
    | 'gray-transparent'
    | 'red-transparent'
    | 'blue-fill'
    | 'blue-stroke'
    | 'violet-fill'
    | 'violet-stroke'
    | 'gray-stroke'
    | 'red-stroke'
    | 'main-fill';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    dimension?: ButtonDimension;
    appearance?: ButtonAppearance;
    icon?: React.ReactNode;
    showLoading?: boolean;
    displayAsRound?: boolean;
    direction?: ButtonDirection;
}

const Button: React.FC<ButtonProps> = ({
    className,
    dimension = 'm',
    appearance = 'gray-stroke',
    type = 'button',
    icon,
    displayAsRound,
    children,
    showLoading,
    direction = 'left',
    ...rest
}) => {
    const [color, styleType] = appearance.split('-');

    return (
        <button
            className={cn(
                css.button,
                className,
                `dimension-${dimension}`,
                `direction-${direction}`,
                `color-${color}`,
                `type-${styleType}`,
                {
                    [css.round]: displayAsRound,
                },
            )}
            type={type}
            {...rest}
        >
            {icon && <div className={css.icon}>{icon}</div>}

            {showLoading && (
                <div className={css.loading}>
                    <LoadingIcon />
                </div>
            )}

            {children && <div className={css.content}>{children}</div>}
        </button>
    );
};

export default Button;
