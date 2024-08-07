import React from 'react';

export const FIELD_NAMES = {
    CREDENTIALS: {
        TYPE: 'creds.type',
        ACCESS_KEY: 'creds.access_key',
        SECRET_KEY: 'creds.secret_key',
    },
    VPC_NAME: 'vpc_name',
    REGIONS: 'regions',
};

export const CREDENTIALS_HELP = {
    header: <h2>Credentials</h2>,
    body: (
        <>
            <p>
                To use AWS with <i>dstack</i>, you'll need to create an IAM user in your AWS account, grant this user
                permissions to perform actions on <i>S3</i>, <i>CloudWatch Logs</i>, <i>Secrets Manager</i>, <i>EC2</i>, and{' '}
                <i>IAM</i> services, create credentials for that user, and specify them here as the <i>Access key ID</i> and{' '}
                <i>Secret access</i> key.
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

export const VPC_HELP = {
    header: <h2>VPC</h2>,
    body: (
        <>
            <p>
                Enter <i>VPC name</i> that <i>dstack</i> will use to create resources in your AWS account.
            </p>
        </>
    ),
};

export const REGIONS_HELP = {
    header: <h2>Regions</h2>,
    body: (
        <>
            <p>
                Select <i>Regions</i> that <i>dstack</i> will use to create resources in your AWS account.
            </p>
            <p>
                The selected <i>Regions</i> will be used to run workflows and store artifacts.
            </p>
        </>
    ),
};
