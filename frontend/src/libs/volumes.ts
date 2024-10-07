import { StatusIndicatorProps } from '@cloudscape-design/components';

export const getStatusIconType = (status: IVolume['status']): StatusIndicatorProps['type'] => {
    switch (status) {
        case 'failed':
            return 'error';
        case 'active':
            return 'success';
        case 'provisioning':
            return 'in-progress';
        case 'submitted':
        default:
            console.error(new Error('Undefined volume status'));
    }
};
