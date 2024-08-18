import React, { useState } from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import ace from 'ace-builds';
import CodeEditor, { CodeEditorProps } from '@cloudscape-design/components/code-editor';
import FormField from '@cloudscape-design/components/form-field';

import { CODE_EDITOR_I18N_STRINGS } from './constants';

import { FormCodeEditorProps } from './types';

import 'ace-builds/src-noconflict/mode-yaml';

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
    const [codeEditorPreferences, setCodeEditorPreferences] = useState<CodeEditorProps['preferences']>({
        theme: 'tomorrow_night_bright',
    });

    const onCodeEditorPreferencesChange: CodeEditorProps['onPreferencesChange'] = (e) => {
        setCodeEditorPreferences(e.detail);
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
                        <CodeEditor
                            {...fieldRest}
                            {...props}
                            i18nStrings={CODE_EDITOR_I18N_STRINGS}
                            ace={ace}
                            onChange={(event) => {
                                onChange(event.detail.value);
                                onChangeProp && onChangeProp(event);
                            }}
                            themes={{ light: ['tomorrow_night_bright'], dark: ['tomorrow_night_bright'] }}
                            preferences={codeEditorPreferences}
                            onPreferencesChange={onCodeEditorPreferencesChange}
                        />
                    </FormField>
                );
            }}
        />
    );
};
