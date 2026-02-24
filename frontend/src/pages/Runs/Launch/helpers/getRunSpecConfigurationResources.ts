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
    const { gpu, cpu, memory, shm_size, disk } = (json ?? {}) as { [key: string]: string };
    const result: TDevEnvironmentConfiguration['resources'] = {};

    let gpuResources: TGPUResources = {};

    if (typeof gpu === 'string') {
        const attributes = ((gpu as string) ?? '').split(':');

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
    } else if (typeof gpu === 'object') {
        gpuResources = gpu;
    }

    result['gpu'] = gpuResources;

    if (memory && isMemory(memory)) {
        result['memory'] = parseRange(memory);
    }

    if (shm_size) {
        const shmSizeNum = parseInt(shm_size, 10);

        if (!isNaN(shmSizeNum)) {
            result['shm_size'] = shmSizeNum;
        } else {
            result['shm_size'] = shm_size;
        }
    }

    if (cpu) {
        const cpuNum = parseInt(cpu, 10);

        if (!isNaN(cpuNum)) {
            result['cpu'] = cpuNum;
        } else {
            result['cpu'] = cpu;
        }
    }

    if (disk && isMemory(disk)) {
        result['disk'] = {
            size: parseRange(disk),
        };
    }

    return result;
};
