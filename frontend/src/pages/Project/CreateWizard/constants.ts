export const projectTypeOptions = [
    {
        label: 'Bring your own cloud',
        description: 'Use compute from your own cloud account(s) by providing your credentials.',
        billing_notes:
            "You pay for compute and storage usage directly to the configured cloud provider(s) through their billing. dstack won't bill or charge you.",
        value: 'own_cloud',
    },
    {
        label: 'GPU marketplace',
        description: 'Use compute from multiple cloud providers without needing your own cloud account(s).',
        billing_notes:
            'You pay for compute and storage usage directly to dstack. You can top up your balance in your dstack user settings.',
        value: 'gpu_marketplace',
    },
];
