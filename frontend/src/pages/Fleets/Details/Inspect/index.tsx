import React, { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { CodeEditor, Container, Header, Loader } from 'components';

import { useGetFleetDetailsQuery } from 'services/fleet';

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

    const { data: fleetData, isLoading } = useGetFleetDetailsQuery(
        {
            projectName: paramProjectName,
            fleetId: paramFleetId,
        },
        {
            refetchOnMountOrArgChange: true,
        },
    );

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
                editorContentHeight={600}
                onChange={() => {
                    // Prevent editing - onChange is required but we ignore changes
                }}
            />
        </Container>
    );
};
