import React from 'react';

export const FIELD_NAMES = {
    API_KEY: 'creds.api_key',
    REGIONS: 'regions',
};

export const API_KEY_HELP = {
    header: <h2>API Key</h2>,
    body: (
        <>
            <p>The API key will be used to authenticate dstack server with Lambda API.</p>
        </>
    ),
};

export const REGIONS_HELP = {
    header: <h2>Regions</h2>,
    body: (
        <>
            <p>Select Lambda regions that will be used to provision compute resources.</p>
        </>
    ),
};

export const STORAGE_HELP = {
    header: <h2>Storage</h2>,
    body: (
        <>
            <p>Select storage type that will be used for storing workflow metadata and artifacts.</p>
        </>
    ),
};

export const CREDENTIALS_HELP = {
    header: <h2>AWS Credentials</h2>,
    body: (
        <>
            <p>
                To use AWS S3 as a storage for Lambda, you'll need to create an IAM user in your AWS account, grant this user
                permissions to perform actions on S3, create credentials for that user, and specify them here as the Access key
                ID and Secret access key.
            </p>
        </>
    ),

    footer: (
        <>
            <h3>Learn more</h3>

            <ul>
                <li>
                    <a href="https://docs.aws.amazon.com/cli/latest/userguide/cli-authentication-user.html">
                        Authenticating using IAM user credentials
                    </a>
                </li>
            </ul>
        </>
    ),
};

export const BUCKET_HELP = {
    header: <h2>Bucket</h2>,
    body: (
        <>
            <p>Select an S3 bucket that will be used for storing workflow metadata and artifacts.</p>
        </>
    ),
};
