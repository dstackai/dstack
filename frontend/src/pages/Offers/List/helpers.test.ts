import { rangeToObject } from './helpers';

describe('Offers helpers', () => {
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
