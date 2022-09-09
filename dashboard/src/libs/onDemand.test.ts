import { limitMaximumToString } from './onDemand';

describe('Test on demand libs', () => {
    test('Limit Maximum to string', () => {
        expect(limitMaximumToString(0)).toBe('0');
        expect(limitMaximumToString(10)).toBe('10');
        expect(limitMaximumToString(null)).toBe('');
    });
});
