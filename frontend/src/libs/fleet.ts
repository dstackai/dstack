import { isEqual } from 'lodash';
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

export const getFleetPrice = (fleet: IFleet): number | null => {
    return fleet.instances.reduce<null | number>((acc, instance) => {
        if (typeof instance.price === 'number' && instance.status !== 'terminated') {
            if (acc === null) return instance.price;

            acc += instance.price;
        }

        return acc;
    }, null);
};

const getInstanceFields = (instance: IInstance) => ({
    backend: instance.backend,
    region: instance.region,
    type: instance.instance_type?.name,
    spot: instance.instance_type?.resources.spot,
});

export const getFleetInstancesLinkText = (fleet: IFleet): string => {
    const instances = fleet.instances.filter((i) => i.status !== 'terminated');
    const hasPending = instances.some((i) => i.status === 'pending');

    if (!instances.length) return '0 instances';

    if (hasPending) return `${instances.length} instances`;

    const isSameInstances = instances.every((i) => isEqual(getInstanceFields(instances[0]), getInstanceFields(i)));

    if (isSameInstances)
        return `${instances.length}x ${instances[0].instance_type?.name}${
            instances[0].instance_type?.resources.spot ? ' (spot)' : ''
        } @ ${instances[0].backend} (${instances[0].region})`;

    return `${instances.length} instances`;
};
