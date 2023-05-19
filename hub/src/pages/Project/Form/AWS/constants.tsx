import React from 'react';

export const FIELD_NAMES = {
    ACCESS_KEY: 'access_key',
    SECRET_KEY: 'secret_key',
    REGION_NAME: 'region_name',
    S3_BUCKET_NAME: 's3_bucket_name',
    EC2_SUBNET_ID: 'ec2_subnet_id',
};

export const CREDENTIALS_HELP = {
    header: <h2>Credentials</h2>,
    body: (
        <>
            <p>
                To use AWS with <i>dstack Hub</i>, you'll need to create an IAM user in your AWS account, grant this user
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

export const REGION_HELP = {
    header: <h2>Region</h2>,
    body: (
        <>
            <p>
                Select a <i>Region</i> that <i>dstack Hub</i> will use to create resources in your AWS account.
            </p>
            <p>
                The selected <i>Region</i> will be used to run workflows and store artifacts.
            </p>
        </>
    ),
};

export const BUCKET_HELP = {
    header: <h2>Bucket</h2>,
    body: (
        <>
            <p>
                Select an existing S3 <i>Bucket</i> to store workflow artifacts.
            </p>
            <p>
                Please note that the <i>Bucket</i> must belong to the selected <i>Region</i>, and the user to whom the provided{' '}
                credentials belong must have write permissions to the <i>Bucket</i>.
            </p>
        </>
    ),
};

export const SUBNET_HELP = {
    header: <h2>Backend type</h2>,
    body: (
        <>
            <p>
                Select a <i>Subnet</i> to run workflows in. If no Subnet is specified, <i>dstack Hub</i> will use the default{' '}
                <i>Subnet</i> configured in your AWS account.
            </p>
        </>
    ),
};
