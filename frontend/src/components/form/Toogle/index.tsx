import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import FormField from '@cloudscape-design/components/form-field';
import ToggleCSD from '@cloudscape-design/components/toggle';

import { FormToggleProps } from './types';

export const FormToggle = <T extends FieldValues>({
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
    toggleLabel,
    onChange: onChangeProp,
    toggleDescription,
    ...props
}: FormToggleProps<T>) => {
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

                        <ToggleCSD
                            {...fieldRest}
                            {...props}
                            checked={value}
                            onChange={(event) => {
                                onChange(event.detail.checked);
                                onChangeProp?.(event);
                            }}
                            description={toggleDescription}
                        >
                            {toggleLabel}
                        </ToggleCSD>
                    </FormField>
                );
            }}
        />
    );
};
