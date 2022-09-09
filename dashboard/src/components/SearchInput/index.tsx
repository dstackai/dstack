import React, { useState } from 'react';
import Input, { Props as InputProps } from 'components/Input';
import { ReactComponent as MagnifyIcon } from 'assets/icons/magnify.svg';
import { ReactComponent as CloseIcon } from 'assets/icons/close.svg';
import css from './index.module.css';
import cn from 'classnames';

export interface Props extends Omit<InputProps, 'onChange' | 'type' | 'value' | 'inputElementClassName'> {
    onChange?: (value: string) => void;
    value?: string;
}

const SearchInput: React.FC<Props> = ({ className, onChange, ...props }) => {
    const [value, set] = useState<string | undefined>(props.value);

    const onChangeHandle = (event: React.ChangeEvent<HTMLInputElement>) => {
        set(event.target.value);

        if (onChange) onChange(event.target.value);
    };

    const clearHandle = () => {
        set('');
        if (onChange) onChange('');
    };

    return (
        <div className={cn(css.searchInput, className)}>
            <Input value={value} type="text" onChange={onChangeHandle} inputElementClassName={css.inputElement} {...props} />

            <div className={css.icon}>
                {!value && <MagnifyIcon />}
                {value && (
                    <button onClick={clearHandle}>
                        <CloseIcon />
                    </button>
                )}
            </div>
        </div>
    );
};

export default SearchInput;
