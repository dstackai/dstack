import React, { forwardRef, useState } from 'react';
import cn from 'classnames';
import { refSetter } from 'libs/refSetter';
import Button from 'components/Button';
import { ReactComponent as MarkIcon } from 'assets/icons/mark.svg';
import { ReactComponent as EyeOutlineIcon } from 'assets/icons/eye-outline.svg';
import { ReactComponent as EyeOffOutlineIcon } from 'assets/icons/eye-off-outline.svg';
import css from './index.module.css';

export interface Props extends React.InputHTMLAttributes<HTMLInputElement> {
    inputElementClassName?: string;
    hasError?: boolean;
    dimension?: 's' | 'm';
}

const Input = forwardRef<HTMLInputElement, Props>(
    ({ inputElementClassName, className, dimension = 's', type = 'text', hasError, ...rest }, ref) => {
        const inputRef = React.useRef<HTMLInputElement>(null);

        const [currentType, setCurrentType] = useState<HTMLInputElement['type']>(type);

        const togglePasswordType = () => setCurrentType(currentType === 'password' ? 'text' : 'password');

        return (
            <div className={cn(css.inputWrapper, className, `dimension-${dimension}`, type)}>
                <input
                    className={cn(css.input, inputElementClassName, { [css.withError]: hasError })}
                    {...rest}
                    ref={refSetter(ref, inputRef)}
                    type={currentType}
                />

                {type === 'password' && (
                    <div className={css.togglePassword}>
                        <Button
                            className={css.button}
                            appearance="gray-transparent"
                            displayAsRound
                            icon={currentType === 'password' ? <EyeOffOutlineIcon /> : <EyeOutlineIcon />}
                            onClick={togglePasswordType}
                        />
                    </div>
                )}

                {type === 'checkbox' && (
                    <div className={css.checkbox}>
                        <MarkIcon />
                    </div>
                )}
            </div>
        );
    },
);

export default Input;
