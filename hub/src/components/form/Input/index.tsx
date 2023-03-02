import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import InputCSD from '@cloudscape-design/components/input';
import FormField from '@cloudscape-design/components/form-field';
import { FormInputProps } from './types';

export const FormInput = <T extends FieldValues>({
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
    onChange: onChangeProp,
    ...props
}: FormInputProps<T>) => {
    return (
        <Controller
            name={name}
            control={control}
            rules={rules}
            render={({ field: { onChange, ...fieldRest }, fieldState: { error } }) => {
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
                        <InputCSD
                            {...fieldRest}
                            {...props}
                            invalid={!!error}
                            onChange={(event) => {
                                onChange(event.detail.value);
                                onChangeProp && onChangeProp(event);
                            }}
                        />
                    </FormField>
                );
            }}
        />
    );
};
