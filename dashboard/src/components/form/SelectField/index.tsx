import React, { forwardRef } from 'react';
import Field, { Props as FieldProps } from 'components/form/Field';
import Select, { Props as SelectProps } from 'components/Select';
import cn from 'classnames';
import { refSetter } from 'libs/refSetter';

export interface Props extends Omit<FieldProps, 'children'>, Omit<SelectProps, 'className'> {}

const SelectField = forwardRef<HTMLSelectElement, Props>(({ label, className, error, notRequired, ...selectProps }, ref) => {
    const selectRef = React.useRef<HTMLSelectElement>(null);

    return (
        <Field label={label} className={cn(className)} error={error} notRequired={notRequired}>
            <Select {...selectProps} hasError={Boolean(error)} ref={refSetter(ref, selectRef)} />
        </Field>
    );
});

export default SelectField;
