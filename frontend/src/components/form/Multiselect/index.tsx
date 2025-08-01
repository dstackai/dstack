import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import FormField from '@cloudscape-design/components/form-field';
import MultiselectCSD from '@cloudscape-design/components/multiselect';
import { MultiselectProps } from '@cloudscape-design/components/multiselect/interfaces';

import { FormMultiselectProps } from './types';

export const FormMultiselect = <T extends FieldValues>({
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
}: FormMultiselectProps<T>) => {
    return (
        <Controller
            name={name}
            control={control}
            rules={rules}
            render={({ field: { onChange, ...fieldRest }, fieldState: { error } }) => {
                const selectedOptions = props.options?.filter((i) => fieldRest.value?.includes(i.value)) ?? null;

                const onChangeSelect: MultiselectProps['onChange'] = (event) => {
                    const value = event.detail.selectedOptions.map((item) => item.value);
                    onChange(value);
                    onChangeProp?.(event);
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
                        <MultiselectCSD
                            selectedOptions={selectedOptions}
                            onChange={onChangeSelect}
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
