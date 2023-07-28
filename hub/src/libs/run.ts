import { StatusIndicatorProps } from '@cloudscape-design/components';

export const getStatusIconType = (status: IRun['status']): StatusIndicatorProps['type'] => {
    switch (status) {
        case 'failed':
            return 'error';
        case 'aborted':
        case 'terminated':
            return 'stopped';
        case 'done':
            return 'success';
        case 'building':
        case 'running':
        case 'uploading':
        case 'downloading':
        case 'stopping':
        case 'terminating':
            return 'in-progress';
        case 'submitted':
        case 'pending':
        case 'stopped':
            return 'pending';
        default:
            return 'stopped';
    }
};
