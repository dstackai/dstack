import React, { useEffect, useState } from 'react';
import { Controller, FieldValues } from 'react-hook-form';
import ace from 'ace-builds';
import CodeEditor, { CodeEditorProps } from '@cloudscape-design/components/code-editor';
import FormField from '@cloudscape-design/components/form-field';

import { CODE_EDITOR_I18N_STRINGS } from './constants';

import { FormCodeEditorProps } from './types';

ace.config.set('useWorker', false);

import { Mode } from '@cloudscape-design/global-styles';

import { useAppSelector } from 'hooks';

import { selectSystemMode } from 'App/slice';

import 'ace-builds/src-noconflict/theme-cloud_editor';
import 'ace-builds/src-noconflict/theme-cloud_editor_dark';
import 'ace-builds/src-noconflict/mode-yaml';
import 'ace-builds/src-noconflict/ext-language_tools';

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
    const systemMode = useAppSelector(selectSystemMode) ?? '';

    const [codeEditorPreferences, setCodeEditorPreferences] = useState<CodeEditorProps['preferences']>(() => ({
        theme: systemMode === Mode.Dark ? 'cloud_editor_dark' : 'cloud_editor',
    }));

    useEffect(() => {
        if (systemMode === Mode.Dark)
            setCodeEditorPreferences({
                theme: 'cloud_editor_dark',
            });
        else
            setCodeEditorPreferences({
                theme: 'cloud_editor',
            });
    }, [systemMode]);

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
                                onChangeProp?.(event);
                            }}
                            themes={{ light: [], dark: [] }}
                            preferences={codeEditorPreferences}
                            onPreferencesChange={onCodeEditorPreferencesChange}
                        />
                    </FormField>
                );
            }}
        />
    );
};
