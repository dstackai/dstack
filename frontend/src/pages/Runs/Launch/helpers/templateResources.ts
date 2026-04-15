import { getRunSpecConfigurationResources } from './getRunSpecConfigurationResources';

type TGpuFilterDefaults = {
    gpu_name?: string | string[];
    gpu_count?: string;
    gpu_memory?: string;
};

type TOfferFilterDefaults = TGpuFilterDefaults & {
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

export const hasConfiguredGpu = (template?: ITemplate): boolean => {
    const gpu = getTemplateGpuSpec(template);
    if (typeof gpu === 'number') {
        return gpu > 0;
    }
    if (typeof gpu === 'string') {
        const normalizedGpu = gpu.trim();
        return normalizedGpu !== '' && normalizedGpu !== '0';
    }
    if (gpu && typeof gpu === 'object') {
        return Object.keys(gpu as Record<string, unknown>).length > 0;
    }

    return false;
};

export const getTemplateOfferDefaultFilters = (template?: ITemplate): TOfferFilterDefaults => {
    const gpu = getTemplateGpuSpec(template);
    const configuration = template?.configuration;

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

    if (typeof gpu === 'number') {
        return {
            ...(gpu > 0 ? { gpu_count: String(gpu) } : {}),
            ...(spotPolicy ? { spot_policy: spotPolicy } : {}),
            ...(backends?.length ? { backend: backends } : {}),
            ...(fleets?.length ? { fleet: fleets } : {}),
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
            ...(spotPolicy ? { spot_policy: spotPolicy } : {}),
            ...(backends?.length ? { backend: backends } : {}),
            ...(fleets?.length ? { fleet: fleets } : {}),
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
        ...(typeof gpuName === 'string' ? { gpu_name: gpuName } : {}),
        ...(Array.isArray(gpuName) && gpuName.every((name) => typeof name === 'string') ? { gpu_name: gpuName } : {}),
        ...(gpuCount ? { gpu_count: gpuCount } : {}),
        ...(gpuMemory ? { gpu_memory: gpuMemory } : {}),
        ...(spotPolicy ? { spot_policy: spotPolicy } : {}),
        ...(backends?.length ? { backend: backends } : {}),
        ...(fleets?.length ? { fleet: fleets } : {}),
    };
};
