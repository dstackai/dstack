import React from 'react';

export const FIELD_NAMES = {
    CREDENTIALS: {
        TYPE: 'credentials.type',
        FILENAME: 'credentials.filename',
        DATA: 'credentials.data',
    },
    REGIONS: 'regions',
    BUCKET_NAME: 'bucket_name',
    VPC_SUBNET: 'vpc_subnet',
    VPC: 'vpc',
    SUBNET: 'subnet',
};

export const SERVICE_ACCOUNT_HELP = {
    header: <h2>Service account</h2>,
    body: (
        <>
            <p>
                In order to use GCP with <i>dstack</i>, you'll need to set up a <i>Service account</i> in your GCP project.
            </p>

            <h4>Enable APIs</h4>
            <p>
                Note: Before creating a service account, make sure to enable the following APIs for the GCP project:
                <pre>
                    cloudapis.googleapis.com compute.googleapis.com logging.googleapis.com secretmanager.googleapis.com
                    storage-api.googleapis.com storage-component.googleapis.com storage.googleapis.com
                </pre>
            </p>
            <h4>Create a service account</h4>
            <p>
                Once the required APIs are enabled for the GCP project, you have to create a service account configure the
                following roles for it: <i>Service Account User</i>, <i>Compute Admin</i>,<i>Storage Admin</i>,{' '}
                <i>Secret Manager Admin</i>, and <i>Logging Admin</i>.
            </p>
            <h4>Create a service account key</h4>
            <p>
                Once the service account is set up, create a key for it, download the corresponding JSON file, and upload it
                here.
            </p>
        </>
    ),

    footer: (
        <>
            <h3>Learn more</h3>

            <ul>
                <li>
                    <a href="https://cloud.google.com/iam/docs/service-accounts-create">Create service accounts</a>
                </li>
            </ul>
        </>
    ),
};

export const REGIONS_HELP = {
    header: <h2>Regions</h2>,
    body: (
        <>
            <p>
                Select <i>Regions</i> that <i>dstack</i> will use to create resources in your GCP account.
            </p>
            <p>
                The selected <i>Regions</i> will be used to run workflows and store artifacts.
            </p>
        </>
    ),
};

export const BUCKET_HELP = {
    header: <h2>Bucket</h2>,
    body: (
        <>
            <p>
                Select an existing storage <i>Bucket</i> to store workflow artifacts.
            </p>
            <p>
                Please note that the <i>Bucket</i> must belong to the selected <i>Region</i> the project to which the provided{' '}
                <i>Service account</i> belongs. Furthermore, the configured <i>Service Account</i> must have the necessary write
                permissions for the <i>Bucket</i>.
            </p>
        </>
    ),
};

export const SUBNET_HELP = {
    header: <h2>Subnet</h2>,
    body: (
        <>
            <p>
                Select a <i>Subnet</i> to run workflows in. If no Subnet is specified, <i>dstack</i> will use the default{' '}
                <i>Subnet</i> configured in your AWS account.
            </p>
        </>
    ),
};
