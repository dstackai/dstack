import { formatBytes, mibToBytes } from './index';

export const formatResourcesGPUs = (gpus: IRunnerResources['gpus']) =>
    `${gpus[0].name}${gpus.length > 1 ? 'x' + gpus.length : ''}`;

export const getResourcesString = (resources: IRunnerResources): string => {
    const { gpus, cpu, memory_mib, interruptible } = resources;
    const result: string[] = [];

    if (cpu.count) result.push(`CPU ${cpu.count}`);

    if (memory_mib) result.push(formatBytes(mibToBytes(memory_mib)));

    if (gpus.length) {
        result.push(`GPU ${formatResourcesGPUs(gpus)}`);
    }

    if (interruptible) {
        result.push('Interruptible');
    }

    return result.join(', ');
};
