import { formatBytes, mibToBytes } from './index';

export const formatRequirementsGPU = (gpu: IJobRequirements['gpu']) => {
    if (!gpu) return '';
    let result = '';
    const { name, count } = gpu;

    if (name) {
        result += name;
        if (count && count > 1) result += `x${count}`;
    } else {
        result += `${count}`;
    }

    return result;
};

export const getRequirementsString = (resources: IJobRequirements): string => {
    const { gpu, cpu, memory } = resources;

    const properties: string[] = [];

    if (cpu && cpu.count) properties.push(`CPU ${cpu.count}`);

    if (memory) properties.push(formatBytes(mibToBytes(memory)));

    if (gpu && gpu.name) {
        properties.push(`GPU ${formatRequirementsGPU(gpu)}`);
    }

    return properties.join(', ');
};
