import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import FormField from '@cloudscape-design/components/form-field';
import TextareaCSD from '@cloudscape-design/components/textarea';

import { FormTextareaProps } from './types';

export const FormTextarea = <T extends FieldValues>({
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
}: FormTextareaProps<T>) => {
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
                        <TextareaCSD
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
