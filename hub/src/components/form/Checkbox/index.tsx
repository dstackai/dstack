import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import CheckboxCSD from '@cloudscape-design/components/checkbox';
import FormField from '@cloudscape-design/components/form-field';

import { FormCheckboxProps } from './types';

export const FormCheckbox = <T extends FieldValues>({
    name,
    control,
    rules,
    label,
    info,
    constraintText,
    description,
    secondaryControl,
    stretch,
    leftContent,
    checkboxLabel,
    onChange: onChangeProp,
    ...props
}: FormCheckboxProps<T>) => {
    return (
        <Controller
            name={name}
            control={control}
            rules={rules}
            render={({ field: { onChange, value, ...fieldRest }, fieldState: { error } }) => {
                return (
                    <FormField
                        description={description}
                        label={label}
                        info={info}
                        stretch={stretch}
                        constraintText={constraintText}
                        secondaryControl={secondaryControl}
                        errorText={error?.message}
                    >
                        {leftContent}
                        <CheckboxCSD
                            {...fieldRest}
                            {...props}
                            checked={value}
                            onChange={(event) => {
                                onChange(event.detail.checked);
                                onChangeProp && onChangeProp(event);
                            }}
                        >
                            {checkboxLabel}
                        </CheckboxCSD>
                    </FormField>
                );
            }}
        />
    );
};
