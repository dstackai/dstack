import React from 'react';

import { RequestParam } from '../../../libs/filters';

import styles from './styles.module.scss';

const rangeSeparator = '..';

export function convertMiBToGB(mib: number) {
    return mib / 1024;
}

export const getPropertyFilterOptions = (gpus: (IGpu | ICpuGroup)[]) => {
    const names = new Set<string>();
    const vendors = new Set<string>();
    const backends = new Set<string>();
    const counts = new Set<string>();

    gpus.forEach((gp) => {
        if ('name' in gp) names.add(gp.name);
        if ('vendor' in gp && gp.vendor) vendors.add(gp.vendor);

        if (gp.backend) {
            backends.add(gp.backend);
        }

        if (gp.backends?.length) {
            gp.backends.forEach((i) => backends.add(i));
        }

        const countRange = renderRange(gp.count);

        if (gp.count && countRange) {
            counts.add(countRange);
        }
    });

    return {
        names,
        vendors,
        backends,
        counts,
    };
};

const AVAILABLE_STATUSES = new Set<TAvailability>(['unknown', 'available']);

export const formatGpuVendor = (vendor: string) => (vendor === 'google' ? 'TPU' : vendor.toUpperCase());

export type OfferCard = IGpu & {
    cpu?: IResources & {
        architectures?: ICpuGroup['cpu_arch'];
        memory_range?: ICpuGroup['memory_mib'];
    };
};

export const toCpuCard = ({ cpu_arch, memory_mib, ...group }: ICpuGroup): OfferCard => ({
    ...group,
    name: 'CPU',
    vendor: '',
    memory_mib: memory_mib.min,
    cpu: {
        cpus: group.count.min,
        cpu_arch: cpu_arch.length === 1 ? cpu_arch[0] : null,
        memory_mib: memory_mib.min,
        architectures: cpu_arch,
        memory_range: memory_mib,
        gpus: [],
        spot: group.spot.length === 1 && group.spot[0] === 'spot',
    },
});

export const getCpuMemory = (offer: OfferCard) => {
    const range = offer.cpu?.memory_range ?? { min: offer.memory_mib, max: offer.memory_mib };
    const min = `${convertMiBToGB(range.min)}GB`;
    return range.min === range.max ? min : `${min}..${convertMiBToGB(range.max)}GB`;
};

export const toOfferCard = ({ backend, region, instance: { resources }, price, availability }: IInstanceOffer): OfferCard => {
    const gpu = resources.gpus[0];
    const count = gpu ? resources.gpus.length : resources.cpus;
    return {
        name: gpu?.name ?? 'CPU',
        vendor: gpu?.vendor ?? '',
        memory_mib: gpu?.memory_mib ?? resources.memory_mib,
        count: { min: count, max: count },
        price: { min: price, max: price },
        availability: [availability],
        spot: [resources.spot ? 'spot' : 'on-demand'],
        backend,
        region,
        cpu: gpu ? undefined : resources,
    };
};

export const getOfferResources = (offer: OfferCard): TResourceRequest =>
    offer.cpu
        ? {
              gpu: 0,
              cpu: [offer.cpu.cpu_arch, renderRange(offer.count)].filter(Boolean).join(':'),
              memory: getCpuMemory(offer),
          }
        : {
              gpu: [offer.vendor, offer.name, renderRange(offer.count), `${convertMiBToGB(offer.memory_mib)}GB`]
                  .filter(Boolean)
                  .join(':'),
          };

export const getOfferSearchParams = (searchParams: URLSearchParams, offer?: OfferCard) => {
    const params = new URLSearchParams(searchParams);
    params.delete('group_by');

    if (!offer) return params;

    ['gpu_vendor', 'gpu_name', 'gpu_count', 'gpu_memory'].forEach((key) => params.delete(key));

    if (offer.cpu) {
        params.set('gpu_count', '0');
        params.set('cpu_count', renderRange(offer.count) ?? '1');
        params.delete('cpu_arch');
        if (offer.cpu.cpu_arch) params.set('cpu_arch', offer.cpu.cpu_arch);
        params.set('memory', getCpuMemory(offer));
    } else {
        params.set('gpu_vendor', offer.vendor);
        params.set('gpu_name', offer.name);
        params.set('gpu_count', renderRange(offer.count) ?? '1');
        params.set('gpu_memory', `${convertMiBToGB(offer.memory_mib)}GB`);
    }

    if (offer.backend) params.set('backend', offer.backend);
    if (offer.region) params.set('region', offer.region);
    params.set('spot_policy', offer.spot.length === 1 ? offer.spot[0] : 'auto');
    return params;
};

export const getOfferAvailability = (availability: TAvailability[]) =>
    availability.some((status) => AVAILABLE_STATUSES.has(status))
        ? undefined
        : (['idle', 'not_available', 'no_balance', 'no_quota', 'busy'] as const).find((status) =>
              availability.includes(status),
          );

export const getFleetFilterValue = (fleet: IFleet, selectedProjectName?: string) => {
    if (selectedProjectName && fleet.project_name === selectedProjectName) {
        return fleet.name;
    }

    return `${fleet.project_name}/${fleet.name}`;
};

export const round = (number: number) => Math.round(number * 100) / 100;

export const renderRange = (range: { min?: number; max?: number }) => {
    if (typeof range.min === 'number' && typeof range.max === 'number' && range.max != range.min) {
        return `${round(range.min)}${rangeSeparator}${round(range.max)}`;
    }

    return range.min?.toString() ?? range.max?.toString();
};

export const renderRangeJSX = (range: { min?: number; max?: number }) => {
    if (typeof range.min === 'number' && typeof range.max === 'number' && range.max != range.min) {
        return (
            <>
                {Number(range.min.toFixed(2))}
                <span className={styles.greyText}>{rangeSeparator}</span>
                {Number(range.max.toFixed(2))}
            </>
        );
    }

    const value = range.min ?? range.max;
    return value === undefined ? undefined : Number(value.toFixed(2));
};

export const rangeToObject = (
    range: RequestParam | number,
    {
        requireUnit = false,
    }: {
        requireUnit?: boolean;
    } = {},
): { min?: number; max?: number } | undefined => {
    const hasGbUnit = (value?: string) => /gb/i.test(value ?? '');

    if (!range) return;

    if (typeof range === 'string') {
        const [minString, maxString] = range.split(rangeSeparator);
        const normalizeNumericPart = (value?: string) => (value ?? '').replace(/[^\d.]/g, '');
        const parseBound = (value?: string): number | undefined => {
            if (requireUnit && value && !hasGbUnit(value)) {
                return undefined;
            }
            const normalized = normalizeNumericPart(value);
            if (!normalized) {
                return undefined;
            }
            const parsed = Number(normalized);
            return isNaN(parsed) ? undefined : parsed;
        };

        const min = parseBound(minString);
        const max = parseBound(maxString);

        if (!range.includes(rangeSeparator) && typeof min === 'number') {
            return { min, max: min };
        }

        if (typeof min === 'number' && typeof max === 'number') {
            return { min, max };
        }

        if (typeof min === 'number') {
            return { min };
        }

        if (typeof max === 'number') {
            return { max };
        }

        return;
    }

    if (typeof range === 'number') {
        return requireUnit ? undefined : { min: range, max: range };
    }

    return range;
};
