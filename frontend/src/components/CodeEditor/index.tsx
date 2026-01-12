import React, { useEffect, useState } from 'react';
import ace from 'ace-builds';
import GeneralCodeEditor, { CodeEditorProps as GeneralCodeEditorProps } from '@cloudscape-design/components/code-editor';

ace.config.set('useWorker', false);

import { Mode } from '@cloudscape-design/global-styles';

import { useAppSelector } from 'hooks';

import { selectSystemMode } from 'App/slice';

import { CODE_EDITOR_I18N_STRINGS } from './constants';

import 'ace-builds/src-noconflict/theme-cloud_editor';
import 'ace-builds/src-noconflict/theme-cloud_editor_dark';
import 'ace-builds/src-noconflict/mode-yaml';
import 'ace-builds/src-noconflict/mode-json';
import 'ace-builds/src-noconflict/ext-language_tools';

export type CodeEditorProps = Omit<GeneralCodeEditorProps, 'ace' | 'onPreferencesChange' | 'themes' | 'preferences'>;

export const CodeEditor: React.FC<CodeEditorProps> = (props) => {
    const systemMode = useAppSelector(selectSystemMode) ?? '';

    const [codeEditorPreferences, setCodeEditorPreferences] = useState<GeneralCodeEditorProps['preferences']>(() => ({
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

    const onCodeEditorPreferencesChange: GeneralCodeEditorProps['onPreferencesChange'] = (e) => {
        setCodeEditorPreferences(e.detail);
    };

    return (
        <GeneralCodeEditor
            i18nStrings={CODE_EDITOR_I18N_STRINGS}
            ace={ace}
            themes={{ light: [], dark: [] }}
            preferences={codeEditorPreferences}
            onPreferencesChange={onCodeEditorPreferencesChange}
            {...props}
        />
    );
};
