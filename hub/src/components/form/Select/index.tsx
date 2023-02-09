import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import FormField from '@cloudscape-design/components/form-field';
import SelectCSD from '@cloudscape-design/components/select';
import { FormSelectProps } from './types';

export const FormSelect = <T extends FieldValues>({
    name,
    control,
    label,
    info,
    constraintText,
    description,
    secondaryControl,
    stretch,
    ...props
}: FormSelectProps<T>) => {
    return (
        <Controller
            name={name}
            control={control}
            render={({ field: { onChange, ...fieldRest }, fieldState: { error } }) => {
                const selectedOption = props.options?.find((i) => i.value === fieldRest.value) ?? null;

                return (
                    <FormField
                        description={description}
                        label={label}
                        info={info}
                        stretch={stretch}
                        constraintText={constraintText}
                        secondaryControl={secondaryControl}
                    >
                        <SelectCSD
                            selectedOption={selectedOption}
                            onChange={({ detail }) => onChange(detail.selectedOption.value)}
                            {...fieldRest}
                            {...props}
                            invalid={!!error}
                        />
                    </FormField>
                );
            }}
        />
    );
};
