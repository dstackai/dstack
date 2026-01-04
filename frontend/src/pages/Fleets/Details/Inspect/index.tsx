import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import ace from 'ace-builds';
import CodeEditor, { CodeEditorProps } from '@cloudscape-design/components/code-editor';
import { Mode } from '@cloudscape-design/global-styles';

import { Container, Header, Loader } from 'components';
import { CODE_EDITOR_I18N_STRINGS } from 'components/form/CodeEditor/constants';

import { useAppSelector } from 'hooks';
import { useGetFleetDetailsQuery } from 'services/fleet';

import { selectSystemMode } from 'App/slice';

import 'ace-builds/src-noconflict/theme-cloud_editor';
import 'ace-builds/src-noconflict/theme-cloud_editor_dark';
import 'ace-builds/src-noconflict/mode-json';
import 'ace-builds/src-noconflict/ext-language_tools';

ace.config.set('useWorker', false);

interface AceEditorElement extends HTMLElement {
    env?: {
        editor?: {
            setReadOnly: (readOnly: boolean) => void;
        };
    };
}

export const FleetInspect = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramFleetId = params.fleetId ?? '';

    const systemMode = useAppSelector(selectSystemMode) ?? '';

    const { data: fleetData, isLoading } = useGetFleetDetailsQuery(
        {
            projectName: paramProjectName,
            fleetId: paramFleetId,
        },
        {
            refetchOnMountOrArgChange: true,
        },
    );

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

    const jsonContent = useMemo(() => {
        if (!fleetData) return '';
        return JSON.stringify(fleetData, null, 2);
    }, [fleetData]);

    // Set editor to read-only after it loads
    useEffect(() => {
        const timer = setTimeout(() => {
            // Find the ace editor instance in the DOM
            const editorElements = document.querySelectorAll('.ace_editor');
            editorElements.forEach((element: Element) => {
                const aceEditor = (element as AceEditorElement).env?.editor;
                if (aceEditor) {
                    aceEditor.setReadOnly(true);
                }
            });
        }, 100);

        return () => clearTimeout(timer);
    }, [jsonContent]);

    if (isLoading)
        return (
            <Container>
                <Loader />
            </Container>
        );

    return (
        <Container header={<Header variant="h2">{t('fleets.inspect')}</Header>}>
            <CodeEditor
                value={jsonContent}
                language="json"
                i18nStrings={CODE_EDITOR_I18N_STRINGS}
                ace={ace}
                themes={{ light: [], dark: [] }}
                preferences={codeEditorPreferences}
                onPreferencesChange={onCodeEditorPreferencesChange}
                editorContentHeight={600}
                onChange={() => {
                    // Prevent editing - onChange is required but we ignore changes
                }}
            />
        </Container>
    );
};
