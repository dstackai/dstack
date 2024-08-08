import React from 'react';

export const FIELD_NAMES = {
    CREDENTIALS: {
        TYPE: 'creds.type',
        FILENAME: 'creds.filename',
        DATA: 'creds.data',
    },
    REGIONS: 'regions',
    PROJECT_ID: 'project_id',
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

export const PROJECT_ID_HELP = {
    header: <h2>Project Id</h2>,
    body: (
        <>
            <p>
                Select <i>Project Id</i>
            </p>
            <p>
                The selected <i>Project Id</i> will be used to run workflows and store artifacts.
            </p>
        </>
    ),
};
