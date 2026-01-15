import React, { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { CodeEditor, Container, Header, Loader } from 'components';

import { useGetRunQuery } from 'services/run';

interface AceEditorElement extends HTMLElement {
    env?: {
        editor?: {
            setReadOnly: (readOnly: boolean) => void;
        };
    };
}

export const RunInspect = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunId = params.runId ?? '';

    const { data: runData, isLoading } = useGetRunQuery({
        project_name: paramProjectName,
        id: paramRunId,
    });

    const jsonContent = useMemo(() => {
        if (!runData) return '';
        return JSON.stringify(runData, null, 2);
    }, [runData]);

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
        <Container header={<Header variant="h2">{t('projects.run.inspect')}</Header>}>
            <CodeEditor
                value={jsonContent}
                language="json"
                editorContentHeight={600}
                onChange={() => {
                    // Prevent editing - onChange is required but we ignore changes
                }}
            />
        </Container>
    );
};
