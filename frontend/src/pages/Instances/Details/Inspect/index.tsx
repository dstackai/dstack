import React, { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { CodeEditor, Container, Header, Loader } from 'components';

import { useGetInstanceDetailsQuery } from 'services/instance';

interface AceEditorElement extends HTMLElement {
    env?: {
        editor?: {
            setReadOnly: (readOnly: boolean) => void;
        };
    };
}

export const InstanceInspect = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramInstanceId = params.instanceId ?? '';

    const { data, isLoading } = useGetInstanceDetailsQuery(
        {
            projectName: paramProjectName,
            instanceId: paramInstanceId,
        },
        {
            refetchOnMountOrArgChange: true,
        },
    );

    const jsonContent = useMemo(() => {
        if (!data) return '';
        return JSON.stringify(data, null, 2);
    }, [data]);

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
        <Container header={<Header variant="h2">{t('fleets.instances.inspect')}</Header>}>
            <CodeEditor
                value={jsonContent}
                language="json"
                editorContentHeight={600}
                onChange={() => {}}
            />
        </Container>
    );
};
