const isVendor = (value: string) => ['amd', 'nvidia', 'google', 'tpu', 'intel'].includes(value);
const isMemory = (value: string) => /^\d+GB/.test(value);
const isCount = (value: string) => /^\d+(?:\.\.)*(?:\d+)*$/.test(value);

const parseRange = (rangeString: string) => {
    const [min, max] = rangeString.split('..');

    if (!min && !max) {
        return rangeString;
    }

    const numberMin = parseInt(min, 10);
    const numberMax = parseInt(max, 10);

    return {
        ...(!isNaN(numberMin) ? { min: numberMin } : {}),
        ...(!isNaN(numberMax) ? { max: numberMax } : {}),
    };
};

export const getRunSpecConfigurationResources = (json: unknown): TDevEnvironmentConfiguration['resources'] => {
    const { gpu, cpu, memory, shm_size, disk } = (json ?? {}) as Record<string, unknown>;
    const result: TDevEnvironmentConfiguration['resources'] = {};

    if (typeof gpu === 'number') {
        result['gpu'] = gpu;
    } else if (typeof gpu === 'string') {
        const gpuResources: TGPUResources = {};
        const attributes = gpu.split(':');

        attributes.forEach((attribute, index) => {
            if (isVendor(attribute)) {
                gpuResources.vendor = attribute;
                return;
            }

            if (isMemory(attribute)) {
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                gpuResources.memory = parseRange(attribute);
                return;
            }

            if (isCount(attribute)) {
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                gpuResources.count = parseRange(attribute);
                return;
            }

            if (index < 2) {
                gpuResources.name = attribute.split(',');
                return;
            }
        });
        result['gpu'] = gpuResources;
    } else if (typeof gpu === 'object' && gpu !== null) {
        result['gpu'] = gpu as TGPUResources;
    }

    if (typeof memory === 'string' && isMemory(memory)) {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-expect-error
        result['memory'] = parseRange(memory);
    }

    if (shm_size) {
        const shmSizeStr = String(shm_size);
        const shmSizeNum = parseInt(shmSizeStr, 10);

        if (!isNaN(shmSizeNum)) {
            result['shm_size'] = shmSizeNum;
        } else {
            result['shm_size'] = shmSizeStr;
        }
    }

    if (cpu) {
        const cpuStr = String(cpu);
        const cpuNum = parseInt(cpuStr, 10);

        if (!isNaN(cpuNum)) {
            result['cpu'] = cpuNum;
        } else {
            result['cpu'] = cpuStr;
        }
    }

    if (typeof disk === 'string' && isMemory(disk)) {
        result['disk'] = {
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-expect-error
            size: parseRange(disk),
        };
    }

    return result;
};
