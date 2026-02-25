import { StatusIndicatorProps } from '@cloudscape-design/components';

export const prettyEnumValue = (value: string): string => {
    return value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
};

export const getHealthStatusIconType = (healthStatus: THealthStatus): StatusIndicatorProps['type'] => {
    switch (healthStatus) {
        case 'healthy':
            return 'success';
        case 'warning':
            return 'warning';
        case 'failure':
            return 'error';
        default:
            return 'info';
    }
};

export const formatInstanceStatusText = (instance: IInstance): string => {
    const status = instance.status;

    if (
        (status === 'idle' || status === 'busy') &&
        instance.total_blocks !== null &&
        instance.total_blocks > 1
    ) {
        return `${instance.busy_blocks}/${instance.total_blocks} Busy`;
    }

    return prettyEnumValue(status);
};
