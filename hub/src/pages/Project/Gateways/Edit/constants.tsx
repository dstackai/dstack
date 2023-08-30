import React from 'react';

export const WILDCARD_DOMAIN_HELP = {
    header: <h2>Wildcard domain</h2>,
    body: (
        <>
            <p>
                Create a wildcard A record in your DNS provider pointing to the gateway's external IP address. Once created,
                specify the corresponding wildcard domain name here.
            </p>

            <p>
                If you've configured a wildcard domain for the gateway, <i>dstack</i> enables HTTPS automatically and serves the
                services at <code>https://&lt;run name&gt;.&lt;your domain name&gt;</code>
            </p>
        </>
    ),
};
