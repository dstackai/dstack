import React from 'react';

export const BACKENDS_HELP_SKY = {
    header: <h2>Backends</h2>,
    body: (
        <>
            <p>
                To use <code>dstack</code> with cloud providers, you have to configure backends.
            </p>
            <h4>Marketplace</h4>
            <p>
                By default, <code>dstack Sky</code> includes a preset of backends that let you access compute from the{' '}
                <code>dstack</code> marketplace and pay through your <code>dstack Sky</code> user billing.
            </p>
            <h4>Your own cloud accounts</h4>
            <p>
                You can also configure custom backends to use your own cloud providers, either instead of or in addition to the
                default ones.
            </p>
            <p>
                See the{' '}
                <a href={'https://dstack.ai/docs/concepts/backends'} target="_blank">
                    documentation
                </a>{' '}
                for the list of supported backends.
            </p>
        </>
    ),
};

export const BACKENDS_HELP_ENTERPRISE = {
    header: <h2>Backends</h2>,
    body: (
        <>
            <p>
                To use <code>dstack</code> with cloud providers, you have to configure backends.
            </p>
            <p>
                See the{' '}
                <a href={'https://dstack.ai/docs/concepts/backends'} target="_blank">
                    documentation
                </a>{' '}
                for the list of supported backends.
            </p>
        </>
    ),
};
