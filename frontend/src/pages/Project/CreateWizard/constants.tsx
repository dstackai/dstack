import React from 'react';

export const projectTypeOptions = [
    {
        label: 'GPU marketplace',
        description:
            'Find the cheapest GPUs available in our marketplace. Enjoy $5 in free credits, and easily top up your balance with a credit card.',
        value: 'gpu_marketplace',
    },
    {
        label: 'Your cloud accounts',
        description: 'Connect and manage your cloud accounts. dstack supports all major GPU cloud providers.',
        value: 'own_cloud',
    },
];

export const FLEET_MIN_INSTANCES_INFO = {
    header: <h2>Min number of instances</h2>,
    body: (
        <>
            <p>Some text</p>
        </>
    ),
};

export const FLEET_MAX_INSTANCES_INFO = {
    header: <h2>Max number of instances</h2>,
    body: (
        <>
            <p>Some text</p>
        </>
    ),
};

export const FLEET_IDLE_DURATION_INFO = {
    header: <h2>Idle duration</h2>,
    body: (
        <>
            <p>Some text</p>
        </>
    ),
};
