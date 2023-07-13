import React from 'react';

export const FIELD_NAMES = {
    API_KEY: 'api_key',
    REGIONS: 'regions',
    STORAGE_BACKEND: {
        TYPE: 'storage_backend.type',
        BUCKET_NAME: 'storage_backend.bucket_name',
        CREDENTIALS: {
            ACCESS_KEY: 'storage_backend.credentials.access_key',
            SECRET_KEY: 'storage_backend.credentials.secret_key',
        },
    },
};

export const DEFAULT_HELP = {
    header: <h2>HELP TITLE</h2>,
    body: (
        <>
            <p>Help description</p>
        </>
    ),

    footer: (
        <>
            <h3>Help footer</h3>

            <ul>
                <li>
                    <a href="/">Help link</a>
                </li>
            </ul>
        </>
    ),
};
