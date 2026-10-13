import { rangeToObject, sortGpusByPriceDesc } from './helpers';

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
    test('sortGpusByPriceDesc puts available GPUs first, most expensive first', () => {
        const gpus = [
            makeGpu('A10', { min: 0.5, max: 4 }),
            makeGpu('B200', { min: 6, max: 48 }, ['not_available']),
            makeGpu('H100', { min: 2, max: 16 }),
            makeGpu('H200', { min: 3, max: 24 }, ['no_quota', 'idle']),
            makeGpu('L4', { min: 0.5, max: 2 }),
        ];

        expect(sortGpusByPriceDesc(gpus).map(({ name }) => name)).toEqual(['H200', 'H100', 'A10', 'L4', 'B200']);
    });

    test('rangeToObject parses open and closed ranges', () => {
        expect(rangeToObject('1..')).toEqual({ min: 1 });
        expect(rangeToObject('..4')).toEqual({ max: 4 });
        expect(rangeToObject('1..4')).toEqual({ min: 1, max: 4 });
    });

    test('rangeToObject parses GB ranges for memory', () => {
        expect(rangeToObject('24GB..', { requireUnit: true })).toEqual({ min: 24 });
        expect(rangeToObject('..80GB', { requireUnit: true })).toEqual({ max: 80 });
        expect(rangeToObject('40GB..80GB', { requireUnit: true })).toEqual({ min: 40, max: 80 });
    });

    test('rangeToObject rejects unitless memory when unit is required', () => {
        expect(rangeToObject('24..80', { requireUnit: true })).toBeUndefined();
        expect(rangeToObject(24, { requireUnit: true })).toBeUndefined();
    });
});
