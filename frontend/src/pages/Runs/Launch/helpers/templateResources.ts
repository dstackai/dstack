import { getRunSpecConfigurationResources } from './getRunSpecConfigurationResources';

type TGpuFilterDefaults = {
    gpu_name?: string | string[];
    gpu_count?: string;
    gpu_memory?: string;
};

type TOfferFilterDefaults = TGpuFilterDefaults & {
    gpu_vendor?: string;
    cpu_count?: string;
    cpu_arch?: string;
    memory?: string;
    backend?: string | string[];
    fleet?: string | string[];
    spot_policy?: string;
};

const formatRangeForFilter = (
    value: unknown,
    {
        stripGB = false,
        appendGBToNumber = false,
        requireUnitForString = false,
    }: {
        stripGB?: boolean;
        appendGBToNumber?: boolean;
        requireUnitForString?: boolean;
    } = {},
): string | undefined => {
    const hasGbUnit = (token: string) => /gb/i.test(token);

    const normalizeToken = (token: unknown): string | undefined => {
        if (typeof token === 'number') {
            return appendGBToNumber ? `${token}GB` : String(token);
        }
        if (typeof token === 'string') {
            if (requireUnitForString && !hasGbUnit(token)) {
                return undefined;
            }
            const normalized = stripGB ? token.replace(/GB/gi, '').trim() : token.trim();
            return normalized || undefined;
        }
        return undefined;
    };

    if (typeof value === 'number') {
        return normalizeToken(value);
    }
    if (typeof value === 'string') {
        return normalizeToken(value);
    }
    if (value && typeof value === 'object') {
        const min = (value as Record<string, unknown>).min;
        const max = (value as Record<string, unknown>).max;
        const minValue = normalizeToken(min);
        const maxValue = normalizeToken(max);
        const hasMin = !!minValue;
        const hasMax = !!maxValue;
        if (hasMin && minValue === maxValue) {
            return minValue;
        }
        if (hasMin && hasMax) {
            return `${minValue}..${maxValue}`;
        }
        if (hasMin) {
            return `${minValue}..`;
        }
        if (hasMax) {
            return `..${maxValue}`;
        }
    }

    return undefined;
};

const getTemplateGpuSpec = (template?: ITemplate): TResourceRequest['gpu'] | undefined => {
    const resources = template?.configuration?.resources;
    if (!resources || typeof resources !== 'object') {
        return undefined;
    }

    return getRunSpecConfigurationResources(resources)?.gpu;
};

export const getTemplateOfferDefaultFilters = (template?: ITemplate): TOfferFilterDefaults => {
    const gpu = getTemplateGpuSpec(template);
    const configuration = template?.configuration;
    const resources = configuration?.resources as TResourceRequest | undefined;
    const cpu = resources?.cpu;
    const cpuTokens = typeof cpu === 'string' ? cpu.split(':') : [];
    const cpuArch = typeof cpu === 'object' ? cpu?.arch : cpuTokens.find((token) => ['arm', 'x86'].includes(token));
    const cpuCount = formatRangeForFilter(
        typeof cpu === 'object' ? cpu?.count : typeof cpu === 'number' ? cpu : cpuTokens.find((token) => token !== cpuArch),
    );
    const memory = formatRangeForFilter(resources?.memory, { appendGBToNumber: true });

    const spotPolicy =
        configuration && typeof configuration === 'object' && typeof configuration.spot_policy === 'string'
            ? configuration.spot_policy
            : undefined;
    const backends =
        configuration &&
        typeof configuration === 'object' &&
        Array.isArray(configuration.backends) &&
        configuration.backends.every((backend) => typeof backend === 'string')
            ? (configuration.backends as string[])
            : undefined;
    const fleets =
        configuration &&
        typeof configuration === 'object' &&
        Array.isArray(configuration.fleets) &&
        configuration.fleets.every((fleet) => typeof fleet === 'string')
            ? (configuration.fleets as string[])
            : undefined;
    const commonFilters = {
        ...(cpuArch ? { cpu_arch: cpuArch } : {}),
        ...(cpuCount ? { cpu_count: cpuCount } : {}),
        ...(memory ? { memory } : {}),
        ...(spotPolicy ? { spot_policy: spotPolicy } : {}),
        ...(backends?.length ? { backend: backends } : {}),
        ...(fleets?.length ? { fleet: fleets } : {}),
    };

    if (typeof gpu === 'number') {
        return {
            gpu_count: String(gpu),
            ...commonFilters,
        };
    }

    if (typeof gpu === 'string') {
        // Keep fallback for unknown string forms not normalized into object shape.
        const tokens = gpu
            .split(':')
            .map((token) => token.trim())
            .filter(Boolean);
        const gpuNames = tokens[0]
            ?.split(',')
            .map((name) => name.trim())
            .filter(Boolean);

        return {
            ...(gpuNames?.length === 1 ? { gpu_name: gpuNames[0] } : {}),
            ...(gpuNames && gpuNames.length > 1 ? { gpu_name: gpuNames } : {}),
            ...commonFilters,
        };
    }

    const gpuName = gpu && typeof gpu === 'object' ? gpu.name : undefined;
    const gpuCount =
        gpu && typeof gpu === 'object'
            ? formatRangeForFilter(gpu.count, {
                  stripGB: true,
                  appendGBToNumber: false,
              })
            : undefined;
    const gpuMemory =
        gpu && typeof gpu === 'object'
            ? formatRangeForFilter(gpu.memory, {
                  stripGB: false,
                  appendGBToNumber: true,
                  requireUnitForString: true,
              })
            : undefined;

    return {
        ...commonFilters,
        ...(gpu && typeof gpu === 'object' && gpu.vendor ? { gpu_vendor: gpu.vendor } : {}),
        ...(typeof gpuName === 'string' ? { gpu_name: gpuName } : {}),
        ...(Array.isArray(gpuName) && gpuName.every((name) => typeof name === 'string')
            ? { gpu_name: gpuName.length === 1 ? gpuName[0] : gpuName }
            : {}),
        ...(gpuCount ? { gpu_count: gpuCount } : {}),
        ...(gpuMemory ? { gpu_memory: gpuMemory } : {}),
    };
};
