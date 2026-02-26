const mibToGB = (mib: number): string => `${Math.round(mib / 1024)}GB`;

export const formatResources = (resources: IResources, includeSpot = true): string => {
    const parts: string[] = [];

    if (resources.cpus > 0) {
        const archPrefix = resources.cpu_arch === 'arm' ? 'arm:' : '';
        parts.push(`cpu=${archPrefix}${resources.cpus}`);
    }

    if (resources.memory_mib > 0) {
        parts.push(`mem=${mibToGB(resources.memory_mib)}`);
    }

    if (resources.disk && resources.disk.size_mib > 0) {
        parts.push(`disk=${mibToGB(resources.disk.size_mib)}`);
    }

    if (resources.gpus.length > 0) {
        const gpu = resources.gpus[0];
        const gpuParts: string[] = [];

        if (gpu.memory_mib > 0) {
            gpuParts.push(mibToGB(gpu.memory_mib));
        }

        gpuParts.push(String(resources.gpus.length));

        parts.push('gpu=' + [gpu.name, ...gpuParts].filter(Boolean).join(':'));
    }

    let output = parts.join(' ');

    if (includeSpot && resources.spot) {
        output += ' (spot)';
    }

    return output || '-';
};
