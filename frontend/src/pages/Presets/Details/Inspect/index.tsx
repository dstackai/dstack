import React, { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { CodeEditor, Container, Header, Loader } from 'components';

import { useGetPresetQuery } from 'services/preset';

interface AceEditorElement extends HTMLElement {
    env?: {
        editor?: {
            setReadOnly: (readOnly: boolean) => void;
        };
    };
}

export const PresetInspect: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramPresetId = params.presetId ?? '';

    const { data, isLoading } = useGetPresetQuery({
        project_name: paramProjectName,
        id: paramPresetId,
    });

    const jsonContent = useMemo(() => {
        if (!data) return '';
        return JSON.stringify(data, null, 2);
    }, [data]);

    // Set editor to read-only after it loads
    useEffect(() => {
        const timer = setTimeout(() => {
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
        <Container header={<Header variant="h2">{t('presets.inspect')}</Header>}>
            <CodeEditor value={jsonContent} language="json" editorContentHeight={600} />
        </Container>
    );
};
