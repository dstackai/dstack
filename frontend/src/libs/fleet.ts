import { StatusIndicatorProps } from '@cloudscape-design/components';

export const getStatusIconType = (status: IInstance['status']): StatusIndicatorProps['type'] => {
    switch (status) {
        case 'pending':
            return 'pending';
        case 'terminated':
            return 'stopped';
        case 'creating':
        case 'starting':
        case 'provisioning':
        case 'terminating':
            return 'loading';
        case 'busy':
            return 'in-progress';
        case 'idle':
            return 'success';
        default:
            return 'stopped';
    }
};
