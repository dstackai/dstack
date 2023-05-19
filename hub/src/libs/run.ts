import { StatusIndicatorProps } from '@cloudscape-design/components';

export const getStatusIconType = (status: IRun['status']): StatusIndicatorProps['type'] => {
    switch (status) {
        case 'failed':
            return 'error';
        case 'aborted':
        case 'stopped':
            return 'stopped';
        case 'done':
            return 'success';
        case 'running':
        case 'uploading':
        case 'downloading':
            return 'in-progress';
        case 'submitted':
        case 'pending':
            return 'pending';
        default:
            return 'stopped';
    }
};
