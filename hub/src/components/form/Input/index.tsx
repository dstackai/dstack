import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import InputCSD from '@cloudscape-design/components/input';
import FormField from '@cloudscape-design/components/form-field';
import { FormInputProps } from './types';

export const FormInput = <T extends FieldValues>({
    name,
    control,
    label,
    info,
    constraintText,
    description,
    secondaryControl,
    stretch,
    ...props
}: FormInputProps<T>) => {
    return (
        <Controller
            name={name}
            control={control}
            render={({ field, fieldState: { error } }) => {
                return (
                    <FormField
                        description={description}
                        label={label}
                        info={info}
                        stretch={stretch}
                        constraintText={constraintText}
                        secondaryControl={secondaryControl}
                    >
                        <InputCSD {...field} {...props} invalid={!!error} />
                    </FormField>
                );
            }}
        />
    );
};
