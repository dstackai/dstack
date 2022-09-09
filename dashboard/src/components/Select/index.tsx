import React, { forwardRef } from 'react';
import cn from 'classnames';
import { ReactComponent as ChevronDownIcon } from 'assets/icons/chevron-down.svg';
import { refSetter } from 'libs/refSetter';
import css from './index.module.css';

export interface Props extends React.SelectHTMLAttributes<HTMLSelectElement> {
    selectElementClassName?: string;
    options: SelectOption[];
    hasError?: boolean;
}

const Select = forwardRef<HTMLSelectElement, Props>(
    ({ selectElementClassName, className, options, hasError, ...rest }, ref) => {
        const selectRef = React.useRef<HTMLSelectElement>(null);

        return (
            <div className={cn(css.selectWrapper, className)}>
                <select
                    className={cn(css.select, { [css.withError]: hasError }, selectElementClassName)}
                    ref={refSetter(ref, selectRef)}
                    {...rest}
                >
                    {options.map((o, index) => (
                        <option key={index} value={o.value}>
                            {o.title}
                        </option>
                    ))}
                </select>

                <ChevronDownIcon className={css.icon} />
            </div>
        );
    },
);

export default Select;
