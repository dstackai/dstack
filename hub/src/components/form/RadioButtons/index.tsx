import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import FormField from '@cloudscape-design/components/form-field';
import RadioGroup, { RadioGroupProps } from '@cloudscape-design/components/radio-group';

import { FormRadioButtonsProps } from './types';

export const FormRadioButtons = <T extends FieldValues>({
    name,
    rules,
    control,
    label,
    info,
    constraintText,
    description,
    secondaryControl,
    stretch,
    onChange: onChangeProp,
    ...props
}: FormRadioButtonsProps<T>) => {
    return (
        <Controller
            name={name}
            control={control}
            rules={rules}
            render={({ field: { onChange, ...fieldRest }, fieldState: { error } }) => {
                const onChangeSelect: RadioGroupProps['onChange'] = (event) => {
                    onChange(event.detail.value);
                    onChangeProp && onChangeProp(event);
                };

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
                        <RadioGroup onChange={onChangeSelect} {...fieldRest} {...props} />
                    </FormField>
                );
            }}
        />
    );
};
