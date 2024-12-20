import React from 'react';

export const CONFIG_YAML_HELP_SKY = {
    header: <h2>Backend config</h2>,
    body: (
        <>
            <p>
                The backend config is defined in the YAML format. It specifies the backend's <code>type</code> and settings,{' '}
                such as <code>creds</code>, <code>regions</code>, and so on.
            </p>
            <h4>Marketplace</h4>
            <p>
                If you set <code>creds</code>'s <code>type</code> to <code>dstack</code>, you'll get compute from{' '}
                <code>dstack</code>'s marketplace and will pay for it via your <code>dstack Sky</code> user billing. Example:
            </p>
            <p>
                <pre>
                    type: aws{'\n'}
                    creds:{'\n'}
                    {'  '}type: dstack{'\n'}
                </pre>
            </p>
            <p>
                You can see all supported backend types at the{' '}
                <a href={'https://dstack.ai/docs/reference/server/config.yml/#examples'} target={'_blank'}>
                    documentation
                </a>
                .
            </p>
            <h4>Your own cloud account</h4>
            <p>
                If you want to use your own cloud account, configure <code>creds</code> and other settings according to the{' '}
                <a href={'https://dstack.ai/docs/reference/server/config.yml/#examples'} target={'_blank'}>
                    documentation
                </a>
                . Example:
            </p>
            <p>
                <pre>
                    type: aws{'\n'}
                    creds:{'\n'}
                    {'  '}type: access_key{'\n'}
                    {'  '}access_key: AIZKISCVKUK{'\n'}
                    {'  '}secret_key: QSbmpqJIUBn1
                </pre>
            </p>
        </>
    ),
};

export const CONFIG_YAML_HELP_ENTERPRISE = {
    header: <h2>Backend config</h2>,
    body: (
        <>
            <p>
                The backend config is defined in the YAML format. It specifies the backend's <code>type</code> and settings,
                such as <code>creds</code>, <code>regions</code>, and so on.
            </p>
            <p>Example:</p>
            <p>
                <pre>
                    type: aws{'\n'}
                    creds:{'\n'}
                    {'  '}type: access_key{'\n'}
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
