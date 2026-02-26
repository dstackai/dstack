import { isEqual } from 'lodash';
import { StatusIndicatorProps } from '@cloudscape-design/components';

export const formatBackend = (backend: TBackendType | string | null | undefined): string => {
    if (!backend) return '-';
    if (backend === 'remote') return 'ssh';
    return backend;
};

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

const formatRange = (min: unknown, max: unknown, suffix = ''): string => {
    if (min == null && max == null) return '';
    if (min === max) return `${min}${suffix}`;
    if (max == null) return `${min}${suffix}..`;
    if (min == null) return `..${max}${suffix}`;
    return `${min}${suffix}..${max}${suffix}`;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const formatCpu = (cpu: any): string | null => {
    if (!cpu) return null;
    if (typeof cpu === 'number') return `cpu=${cpu}`;
    if (cpu.min != null || cpu.max != null) return `cpu=${formatRange(cpu.min, cpu.max)}`;
    const arch = cpu.arch;
    const count = cpu.count;
    if (!count) return null;
    const prefix = arch === 'arm' ? 'arm:' : '';
    return `cpu=${prefix}${formatRange(count.min, count.max)}`;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const formatGpu = (gpu: any): string | null => {
    if (!gpu) return null;
    const count = gpu.count;
    if (!count || (count.min === 0 && (count.max == null || count.max === 0))) return null;

    const gpuParts: string[] = [];

    if (gpu.memory) {
        const memStr = formatRange(gpu.memory.min, gpu.memory.max, 'GB');
        if (memStr) gpuParts.push(memStr);
    }

    const countStr = formatRange(count.min, count.max);
    if (countStr) gpuParts.push(countStr);

    if (gpu.total_memory) {
        const tmStr = formatRange(gpu.total_memory.min, gpu.total_memory.max, 'GB');
        if (tmStr) gpuParts.push(tmStr);
    }

    let label: string;
    if (gpu.name && gpu.name.length > 0) {
        label = gpu.name.join(',');
    } else if (gpu.vendor) {
        label = gpu.vendor;
    } else {
        label = '';
    }

    return 'gpu=' + [label, ...gpuParts].filter(Boolean).join(':');
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const formatFleetResources = (resources: any): string => {
    if (!resources) return '-';

    const parts: string[] = [];

    const cpuStr = formatCpu(resources.cpu);
    if (cpuStr) parts.push(cpuStr);

    if (resources.memory) {
        const memStr = formatRange(resources.memory.min, resources.memory.max, 'GB');
        if (memStr) parts.push(`mem=${memStr}`);
    }

    if (resources.disk?.size) {
        const diskStr = formatRange(resources.disk.size.min, resources.disk.size.max, 'GB');
        if (diskStr) parts.push(`disk=${diskStr}`);
    }

    const gpuStr = formatGpu(resources.gpu);
    if (gpuStr) parts.push(gpuStr);

    return parts.length > 0 ? parts.join(' ') : '-';
};

export const formatFleetBackend = (config: IFleetConfigurationRequest): string => {
    if (config.ssh_config) return 'ssh';
    if (!config.backends || config.backends.length === 0) return '-';
    return config.backends.map((b) => formatBackend(b)).join(', ');
};

export const getFleetInstancesLinkText = (fleet: IFleet): string => {
    const instances = fleet.instances.filter((i) => i.status !== 'terminated');
    const hasPending = instances.some((i) => i.status === 'pending');

    if (!instances.length) return '0 instances';

    if (hasPending) return `${instances.length} instances`;

    const isSameInstances = instances.every((i) => isEqual(getInstanceFields(instances[0]), getInstanceFields(i)));

    if (isSameInstances)
        return `${instances.length}x ${instances[0].instance_type?.name}${
            instances[0].instance_type?.resources.spot ? ' (spot)' : ''
        } @ ${formatBackend(instances[0].backend)} (${instances[0].region})`;

    return `${instances.length} instances`;
};
