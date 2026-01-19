import React from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import FormField from '@cloudscape-design/components/form-field';

import { CodeEditor } from '../../CodeEditor';

import { FormCodeEditorProps } from './types';

export const FormCodeEditor = <T extends FieldValues>({
    name,
    control,
    rules,
    label,
    info,
    constraintText,
    description,
    secondaryControl,
    stretch,
    onChange: onChangeProp,
    ...props
}: FormCodeEditorProps<T>) => {
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
                        <CodeEditor
                            {...fieldRest}
                            {...props}
                            onChange={(event) => {
                                onChange(event.detail.value);
                                onChangeProp?.(event);
                            }}
                        />
                    </FormField>
                );
            }}
        />
    );
};
