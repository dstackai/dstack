import { StatusIndicatorProps } from '@cloudscape-design/components';

export const getStatusIconType = (status: IInstance['status']): StatusIndicatorProps['type'] => {
    switch (status) {
        case 'pending':
        case 'creating':
            return 'pending';
        case 'terminated':
            return 'stopped';
        case 'terminating':
        case 'provisioning':
        case 'starting':
        case 'busy':
            return 'in-progress';
        case 'idle':
            return 'success';
        default:
            console.error(new Error('Undefined fleet status'));
    }
};

export const getFleetStatusIconType = (status: IFleet['status']): StatusIndicatorProps['type'] => {
    switch (status) {
        case 'submitted':
            return 'pending';
        case 'failed':
        case 'terminated':
            return 'stopped';
        case 'terminating':
            return 'in-progress';
        case 'active':
            return 'success';
        default:
            console.error(new Error('Undefined fleet status'));
    }
};
