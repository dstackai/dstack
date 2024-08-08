import React from 'react';

export const CONFIG_YAML_HELP_SKY = {
    header: <h2>SKy Backend config</h2>,
    body: (
        <>
            <p>
                The backend config is defined in the <code>YAML</code> format. It specifies the backend's <code>type</code> and
                settings, such as <code>creds</code>, <code>regions</code>, and so on.
            </p>
            <p>Example:</p>
            <p>
                <pre>
                    type: aws{'\n'}
                    creds:{'\n'}
                    {'  '}type: default{'\n'}
                    {'  '}access_key: AIZKISCVKUK{'\n'}
                    {'  '}secret_key: QSbmpqJIUBn1
                </pre>
            </p>
            <p>
                Each backend type may support different properties. See the{' '}
                <a href={'https://dstack.ai/docs/reference/server/config.yml/#examples'}>reference page</a> for more examples.
            </p>
        </>
    ),
};

export const CONFIG_YAML_HELP_ENTERPRISE = {
    header: <h2>Enterprise Backend config</h2>,
    body: (
        <>
            <p>
                The backend config is defined in the <code>YAML</code> format. It specifies the backend's <code>type</code> and
                settings, such as <code>creds</code>, <code>regions</code>, and so on.
            </p>
            <p>Example:</p>
            <p>
                <pre>
                    type: aws{'\n'}
                    creds:{'\n'}
                    {'  '}type: default{'\n'}
                    {'  '}access_key: AIZKISCVKUK{'\n'}
                    {'  '}secret_key: QSbmpqJIUBn1
                </pre>
            </p>
            <p>
                Each backend type may support different properties. See the{' '}
                <a href={'https://dstack.ai/docs/reference/server/config.yml/#examples'}>reference page</a> for more examples.
            </p>
        </>
    ),
};
