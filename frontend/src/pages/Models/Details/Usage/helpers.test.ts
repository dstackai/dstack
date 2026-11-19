import {
    DEFAULT_TIME_RANGE,
    getFilteringOptions,
    getUsageRequestParams,
    getUsageTotal,
    getUserOptionsRequestParams,
} from './helpers';

const model = {
    name: 'Qwen/Qwen3.8-Flash-Next',
    project_name: 'exporter-proj',
    endpoints: [],
};

const now = new Date('2026-11-18T23:30:00Z');

describe('Model usage request', () => {
    test('asks for the model by month and project in the last three months by default', () => {
        expect(getUsageRequestParams({ model, timeRange: DEFAULT_TIME_RANGE, period: 'month', filters: {}, now })).toEqual({
            start: '2026-08-01T00:00:00Z',
            end: '2026-12-01T00:00:00Z',
            group_by: ['month', 'project'],
            model_project_name: 'exporter-proj',
            model_name: 'Qwen/Qwen3.8-Flash-Next',
        });
    });

    test.each([
        [{ project_name: 'importer-proj' }],
        [{ user_name: 'bob' }],
        [{ project_name: 'importer-proj', user_name: 'bob' }],
    ])('the filter %j goes to the request, and the rows stay by project', (filters) => {
        const params = getUsageRequestParams({ model, timeRange: DEFAULT_TIME_RANGE, period: 'month', filters, now });

        expect(params).toEqual({
            start: '2026-08-01T00:00:00Z',
            end: '2026-12-01T00:00:00Z',
            group_by: ['month', 'project'],
            model_project_name: 'exporter-proj',
            model_name: 'Qwen/Qwen3.8-Flash-Next',
            ...filters,
        });
    });

    test.each([
        [DEFAULT_TIME_RANGE, '2026-08-18T00:00:00Z', '2026-11-19T00:00:00Z'],
        [{ type: 'relative', amount: 7, unit: 'day' }, '2026-11-11T00:00:00Z', '2026-11-19T00:00:00Z'],
        [{ type: 'absolute', startDate: '2026-11-18', endDate: '2026-11-18' }, '2026-11-18T00:00:00Z', '2026-11-19T00:00:00Z'],
        [{ type: 'absolute', startDate: '2026-10-01', endDate: '2026-10-31' }, '2026-10-01T00:00:00Z', '2026-11-01T00:00:00Z'],
    ] as const)('by day, the time range %j covers whole days', (timeRange, start, end) => {
        const params = getUsageRequestParams({ model, timeRange, period: 'day', filters: {}, now });

        expect(params).toMatchObject({ start, end, group_by: ['day', 'project'] });
    });

    test.each([
        // The running month
        ['2026-11-18', { type: 'relative', amount: 7, unit: 'day' }, '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z'],
        // The seven days cross a month boundary
        ['2026-12-03', { type: 'relative', amount: 7, unit: 'day' }, '2026-11-01T00:00:00Z', '2027-01-01T00:00:00Z'],
        [
            '2026-11-18',
            { type: 'absolute', startDate: '2026-09-03', endDate: '2026-10-10' },
            '2026-09-01T00:00:00Z',
            '2026-11-01T00:00:00Z',
        ],
    ] as const)('by month, on %s the time range %j covers whole months', (today, timeRange, start, end) => {
        const params = getUsageRequestParams({
            model,
            timeRange,
            period: 'month',
            filters: {},
            now: new Date(`${today}T23:30:00Z`),
        });

        expect(params).toMatchObject({ start, end });
    });
});

describe('Model usage filter', () => {
    test("asks for the users of the filter's project in the same time range, whatever user the filter has", () => {
        const filters = { project_name: 'importer-proj', user_name: 'bob' };

        expect(getUserOptionsRequestParams({ model, timeRange: DEFAULT_TIME_RANGE, period: 'month', filters, now })).toEqual({
            start: '2026-08-01T00:00:00Z',
            end: '2026-12-01T00:00:00Z',
            group_by: ['month', 'user'],
            model_project_name: 'exporter-proj',
            model_name: 'Qwen/Qwen3.8-Flash-Next',
            project_name: 'importer-proj',
        });
    });

    test('offers each user of the rows once', () => {
        const rows = ['2026-11-01', '2026-10-01'].flatMap((month) =>
            ['carol', 'bob'].map((user_name) => ({
                month,
                user_name,
                input_tokens: 1,
                cached_input_tokens: 0,
                output_tokens: 0,
            })),
        );

        expect(getFilteringOptions(rows, [])).toEqual([
            { propertyKey: 'user_name', value: 'bob' },
            { propertyKey: 'user_name', value: 'carol' },
        ]);
    });
});

describe('Model usage total', () => {
    test('sums the rows', () => {
        const rows: IMeteringRow[] = [
            {
                day: '2026-12-03',
                project_name: 'importer-proj',
                input_tokens: 50211,
                cached_input_tokens: 41980,
                output_tokens: 6120,
            },
            {
                day: '2026-12-03',
                project_name: 'exporter-proj',
                input_tokens: 8707,
                cached_input_tokens: 7688,
                output_tokens: 423,
            },
        ];

        expect(getUsageTotal(rows)).toEqual({ input_tokens: 58918, cached_input_tokens: 49668, output_tokens: 6543 });
    });
});
