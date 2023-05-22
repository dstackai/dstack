import React from 'react';

export const FIELD_NAMES = {
    TENANT_ID: 'tenant_id',
    CLIENT_ID: 'client_id',
    CLIENT_SECRET: 'client_secret',
    SUBSCRIPTION_ID: 'subscription_id',
    LOCATION: 'location',
    STORAGE_ACCOUNT: 'storage_account',
};

export const CREDENTIALS_HELP = {
    header: <h2>Credentials</h2>,
    body: (
        <>
            <p>
                To use Azure with <i>dstack Hub</i>, you'll need to create an Azure Active Directory app and specify the app
                credentials as the <i>Tenant ID</i>, <i>Client ID</i> and <i>Client secret</i> fields.
            </p>
        </>
    ),
};

export const SUBSCRIPTION_HELP = {
    header: <h2>Subscription ID</h2>,
    body: (
        <>
            <p>
                Select a <i>Subscription ID</i> that <i>dstack Hub</i> will use to create resources in your Azure account.
            </p>
        </>
    ),
};

export const LOCATION_HELP = {
    header: <h2>Location</h2>,
    body: (
        <>
            <p>
                Select a <i>Location</i> that <i>dstack Hub</i> will use to create resources in your Azure account.
            </p>
            <p>
                The selected <i>Location</i> will be used to run workflows and store artifacts.
            </p>
        </>
    ),
};

export const STORAGE_ACCOUNT_HELP = {
    header: <h2>Storage account</h2>,
    body: (
        <>
            <p>
                Select a <i>Storage account</i> to store artifacts. The <i>Storage account</i> should be in the <i>Location</i>{' '}
                selected.
            </p>
            <p>
                <i>dstack Hub</i> will create all the Azure resource in the resource group of the specified{' '}
                <i>Storage account</i>.
            </p>
        </>
    ),
};
