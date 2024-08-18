import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import FormField from '@cloudscape-design/components/form-field';
import Hotspot from '@cloudscape-design/components/hotspot';
import InputCSD, { InputProps } from '@cloudscape-design/components/input';

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
    hotspotId,
    onChange: onChangeProp,
    ...props
}: FormInputProps<T>) => {
    const renderInput = (renderProps: InputProps) => {
        return <InputCSD {...renderProps} />;
    };

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

                        {hotspotId ? (
                            <Hotspot hotspotId={hotspotId}>
                                {renderInput({
                                    ...fieldRest,
                                    ...props,
                                    invalid: !!error,
                                    onChange: (event) => {
                                        onChange(event.detail.value);
                                        onChangeProp && onChangeProp(event);
                                    },
                                })}
                            </Hotspot>
                        ) : (
                            renderInput({
                                ...fieldRest,
                                ...props,
                                invalid: !!error,
                                onChange: (event) => {
                                    onChange(event.detail.value);
                                    onChangeProp && onChangeProp(event);
                                },
                            })
                        )}
                    </FormField>
                );
            }}
        />
    );
};
