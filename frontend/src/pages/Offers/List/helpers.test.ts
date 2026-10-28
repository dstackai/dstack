import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import {
    formatGpuVendor,
    getOfferAvailability,
    getOfferResources,
    getOfferSearchParams,
    rangeToObject,
    renderRangeJSX,
    toCpuCard,
    toOfferCard,
} from './helpers';

const makeGpu = (name: string, price: { min: number; max: number }, availability: TAvailability[] = ['available']): IGpu => ({
    name,
    memory_mib: 81920,
    vendor: 'nvidia',
    availability,
    spot: ['on-demand'],
    count: { min: 1, max: 8 },
    price,
});

describe('Offers helpers', () => {
    test.each([
        [{ min: 52.7436, max: 217.54 }, '52.74..217.54'],
        [{ min: 1.236, max: 1.236 }, '1.24'],
        [{ min: 2, max: 2 }, '2'],
    ] as const)('displays price %j as %s', (price, expected) => {
        const html = renderToStaticMarkup(createElement('span', null, renderRangeJSX(price)));

        expect(html.replace(/<[^>]*>/g, '')).toBe(expected);
    });

    test('GPU selection preserves precise memory and explicit fleet scope', () => {
        const gpu = { ...makeGpu('H100', { min: 1, max: 8 }), memory_mib: 275032 };
        const params = getOfferSearchParams(new URLSearchParams('project_name=main&fleet=chosen&group_by=gpu'), gpu);
        expect(params.get('gpu_memory')).toBe('268.5859375GB');
        expect(params.get('gpu_count')).toBe('1..8');
        expect(params.get('fleet')).toBe('chosen');
        expect(params.has('group_by')).toBe(false);
        expect(getOfferResources(gpu)).toEqual({ gpu: 'nvidia:H100:1..8:268.5859375GB' });
        expect(getOfferSearchParams(new URLSearchParams(), gpu).has('fleet')).toBe(false);
    });

    test('CPU selection replaces GPU constraints and keeps the offer location', () => {
        const cpu = {
            ...makeGpu('CPU', { min: 0, max: 0 }),
            count: { min: 2, max: 2 },
            memory_mib: 1901,
            backend: 'kubernetes' as const,
            region: 'cluster',
            cpu: { cpus: 2, cpu_arch: 'arm', memory_mib: 1901, gpus: [], spot: false },
        };
        const params = getOfferSearchParams(new URLSearchParams('gpu_name=H100&gpu_vendor=nvidia&gpu_memory=80GB'), cpu);
        expect(Object.fromEntries(params)).toEqual({
            gpu_count: '0',
            cpu_count: '2',
            cpu_arch: 'arm',
            memory: '1.8564453125GB',
            backend: 'kubernetes',
            region: 'cluster',
            spot_policy: 'on-demand',
        });
        expect(getOfferResources(cpu)).toEqual({ gpu: 0, cpu: 'arm:2', memory: '1.8564453125GB' });
    });

    test('grouped CPU selection preserves ranges without restricting a mixed architecture group', () => {
        const cpu = toCpuCard({
            cpu_arch: ['arm', 'x86'],
            count: { min: 2, max: 32 },
            memory_mib: { min: 8192, max: 65536 },
            price: { min: 0.1, max: 1 },
            backends: ['aws', 'kubernetes'],
            availability: ['available'],
            spot: ['on-demand', 'spot'],
        });
        expect(cpu.cpu?.architectures).toEqual(['arm', 'x86']);
        expect(getOfferResources(cpu)).toEqual({ gpu: 0, cpu: '2..32', memory: '8GB..64GB' });
        expect(Object.fromEntries(getOfferSearchParams(new URLSearchParams('cpu_arch=arm'), cpu))).toEqual({
            gpu_count: '0',
            cpu_count: '2..32',
            memory: '8GB..64GB',
            spot_policy: 'auto',
        });
    });

    test('Google accelerators are displayed as TPU without changing resource values', () => {
        const gpu = { ...makeGpu('v5p', { min: 1, max: 1 }), vendor: 'google' };
        expect(formatGpuVendor(gpu.vendor)).toBe('TPU');
        expect(formatGpuVendor('amd')).toBe('AMD');
        expect(getOfferResources(gpu)).toEqual({ gpu: 'google:v5p:1..8:80GB' });
        expect(getOfferSearchParams(new URLSearchParams(), gpu).get('gpu_vendor')).toBe('google');
    });

    test('individual cards use system RAM for CPUs and per-GPU VRAM for GPUs, keeping the whole-offer price', () => {
        const resources: IResources = { cpus: 8, cpu_arch: 'arm', memory_mib: 32768, gpus: [], spot: false };
        const offer: IInstanceOffer = {
            backend: 'aws',
            region: 'eu-west-1',
            instance: { name: 'test', resources },
            price: 2,
            availability: 'available',
        };
        const cpu = toOfferCard(offer);
        expect(cpu.cpu?.cpu_arch).toBe('arm');
        expect(cpu.count).toEqual({ min: 8, max: 8 });
        expect(cpu.memory_mib).toBe(32768);

        resources.gpus = [makeGpu('H100', { min: 1, max: 1 }), makeGpu('H100', { min: 1, max: 1 })];
        const gpu = toOfferCard(offer);
        expect(gpu.cpu).toBeUndefined();
        expect(gpu.name).toBe('H100');
        expect(gpu.count).toEqual({ min: 2, max: 2 });
        expect(gpu.memory_mib).toBe(81920);
        expect(gpu.price).toEqual({ min: 2, max: 2 });
    });

    test.each([
        [['no_quota', 'no_balance', 'not_available'], 'not_available'],
        [['no_quota', 'no_balance'], 'no_balance'],
        [['no_quota'], 'no_quota'],
        [['idle'], 'idle'],
        [['busy'], 'busy'],
        [['no_quota', 'available'], undefined],
        [['not_available', 'idle'], 'idle'],
        [['busy', 'idle'], 'idle'],
        [['idle', 'available'], undefined],
        [['no_balance', 'unknown'], undefined],
        [[], undefined],
    ] as [TAvailability[], TAvailability | undefined][])('availability %j shows %s', (statuses, expected) =>
        expect(getOfferAvailability(statuses)).toBe(expected),
    );

    test('rangeToObject parses open and closed ranges', () => {
        expect(rangeToObject('0')).toEqual({ min: 0, max: 0 });
        expect(rangeToObject('2')).toEqual({ min: 2, max: 2 });
        expect(rangeToObject('1..')).toEqual({ min: 1 });
        expect(rangeToObject('..4')).toEqual({ max: 4 });
        expect(rangeToObject('1..4')).toEqual({ min: 1, max: 4 });
    });

    test('rangeToObject parses GB ranges for memory', () => {
        expect(rangeToObject('1.8603515625GB', { requireUnit: true })).toEqual({ min: 1.8603515625, max: 1.8603515625 });
        expect(rangeToObject('24GB..', { requireUnit: true })).toEqual({ min: 24 });
        expect(rangeToObject('..80GB', { requireUnit: true })).toEqual({ max: 80 });
        expect(rangeToObject('40GB..80GB', { requireUnit: true })).toEqual({ min: 40, max: 80 });
    });

    test('rangeToObject rejects unitless memory when unit is required', () => {
        expect(rangeToObject('24..80', { requireUnit: true })).toBeUndefined();
        expect(rangeToObject(24, { requireUnit: true })).toBeUndefined();
    });
});
