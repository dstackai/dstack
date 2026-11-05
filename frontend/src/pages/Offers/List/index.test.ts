import { getRequestParams } from './index';

jest.mock('@cloudscape-design/components/badge', () => ({}));
jest.mock('components', () => ({}));
jest.mock('hooks', () => ({}));
jest.mock('libs', () => ({}));
jest.mock('services/gpu', () => ({}));
jest.mock('./hooks/useFilters', () => ({}));

describe('Offer request parameters', () => {
    test('includes spot and on-demand offers when no spot policy is selected', () => {
        const params = getRequestParams({ project_name: 'main' });

        expect(params.run_spec.configuration.spot_policy).toBe('auto');
    });

    test.each(['spot', 'on-demand', 'auto'] as const)('preserves an explicit %s policy', (spot_policy) => {
        const params = getRequestParams({ project_name: 'main', spot_policy });

        expect(params.run_spec.configuration.spot_policy).toBe(spot_policy);
    });
});
