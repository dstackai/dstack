import React, { forwardRef } from 'react';
import Field, { Props as FieldProps } from 'components/form/Field';
import Input, { Props as InputProps } from 'components/Input';
import cn from 'classnames';
import { refSetter } from 'libs/refSetter';

export interface Props extends Omit<FieldProps, 'children'>, Omit<InputProps, 'className'> {
    children?: React.ReactNode;
}

const InputField = forwardRef<HTMLInputElement, Props>(
    ({ label, notRequired, className, error, children, ...inputProps }, ref) => {
        const inputRef = React.useRef<HTMLInputElement>(null);

        return (
            <Field label={label} className={cn(className)} error={error} notRequired={notRequired}>
                <Input {...inputProps} hasError={Boolean(error)} ref={refSetter(ref, inputRef)} />
                {children}
            </Field>
        );
    },
);

export default InputField;
