import {
    DEFAULT_PERIOD,
    DEFAULT_TIME_RANGES,
    getFilteringOptions,
    getMeteringRequestParams,
    getMeteringTotal,
    getUserOptionsRequestParams,
} from './helpers';

const model = {
    name: 'Qwen/Qwen3.8-Flash-Next',
    project_name: 'exporter-proj',
    endpoints: [],
};

const now = new Date('2026-11-18T23:30:00Z');

describe('Model metering request', () => {
    test('asks for the model by day and project in the last 30 days by default', () => {
        const params = getMeteringRequestParams({
            model,
            timeRange: DEFAULT_TIME_RANGES.day,
            period: DEFAULT_PERIOD,
            filters: {},
            now,
        });

        expect(params).toEqual({
            start: '2026-10-19T00:00:00Z',
            end: '2026-11-19T00:00:00Z',
            group_by: ['day', 'project'],
            model_project_name: 'exporter-proj',
            model_name: 'Qwen/Qwen3.8-Flash-Next',
        });
    });

    test.each([
        [{ project_name: 'importer-proj' }],
        [{ user_name: 'bob' }],
        [{ project_name: 'importer-proj', user_name: 'bob' }],
    ])('the filter %j goes to the request, and the rows stay by project', (filters) => {
        const params = getMeteringRequestParams({
            model,
            timeRange: DEFAULT_TIME_RANGES.day,
            period: DEFAULT_PERIOD,
            filters,
            now,
        });

        expect(params).toEqual({
            start: '2026-10-19T00:00:00Z',
            end: '2026-11-19T00:00:00Z',
            group_by: ['day', 'project'],
            model_project_name: 'exporter-proj',
            model_name: 'Qwen/Qwen3.8-Flash-Next',
            ...filters,
        });
    });

    test.each([
        [{ type: 'relative', amount: 3, unit: 'month' }, '2026-08-18T00:00:00Z', '2026-11-19T00:00:00Z'],
        [{ type: 'relative', amount: 7, unit: 'day' }, '2026-11-11T00:00:00Z', '2026-11-19T00:00:00Z'],
        [{ type: 'absolute', startDate: '2026-11-18', endDate: '2026-11-18' }, '2026-11-18T00:00:00Z', '2026-11-19T00:00:00Z'],
        [{ type: 'absolute', startDate: '2026-10-01', endDate: '2026-10-31' }, '2026-10-01T00:00:00Z', '2026-11-01T00:00:00Z'],
    ] as const)('by day, the time range %j covers whole days', (timeRange, start, end) => {
        const params = getMeteringRequestParams({ model, timeRange, period: 'day', filters: {}, now });

        expect(params).toMatchObject({ start, end, group_by: ['day', 'project'] });
    });

    test('by month, the time range opens on the last 3 months: the running month and the two before it', () => {
        const params = getMeteringRequestParams({
            model,
            timeRange: DEFAULT_TIME_RANGES.month,
            period: 'month',
            filters: {},
            now,
        });

        expect(params).toMatchObject({
            start: '2026-09-01T00:00:00Z',
            end: '2026-12-01T00:00:00Z',
            group_by: ['month', 'project'],
        });
    });

    test.each([
        ['2026-11-18', { type: 'relative', amount: 12, unit: 'month' }, '2025-12-01T00:00:00Z', '2026-12-01T00:00:00Z'],
        ['2026-11-18', { type: 'relative', amount: 1, unit: 'year' }, '2025-12-01T00:00:00Z', '2026-12-01T00:00:00Z'],
        // The months cross a year boundary
        ['2026-01-05', { type: 'relative', amount: 3, unit: 'month' }, '2025-11-01T00:00:00Z', '2026-02-01T00:00:00Z'],
        // The picker's absolute values are months
        [
            '2026-11-18',
            { type: 'absolute', startDate: '2026-09', endDate: '2026-10' },
            '2026-09-01T00:00:00Z',
            '2026-11-01T00:00:00Z',
        ],
        [
            '2026-11-18',
            { type: 'absolute', startDate: '2026-11', endDate: '2026-11' },
            '2026-11-01T00:00:00Z',
            '2026-12-01T00:00:00Z',
        ],
    ] as const)('by month, on %s the time range %j covers whole months', (today, timeRange, start, end) => {
        const params = getMeteringRequestParams({
            model,
            timeRange,
            period: 'month',
            filters: {},
            now: new Date(`${today}T23:30:00Z`),
        });

        expect(params).toMatchObject({ start, end });
    });
});

describe('Model metering filter', () => {
    test("asks for the users of the filter's project in the same time range, whatever user the filter has", () => {
        const filters = { project_name: 'importer-proj', user_name: 'bob' };

        const params = getUserOptionsRequestParams({
            model,
            timeRange: DEFAULT_TIME_RANGES.day,
            period: DEFAULT_PERIOD,
            filters,
            now,
        });

        expect(params).toEqual({
            start: '2026-10-19T00:00:00Z',
            end: '2026-11-19T00:00:00Z',
            group_by: ['day', 'user'],
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

describe('Model metering total', () => {
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

        expect(getMeteringTotal(rows)).toEqual({ input_tokens: 58918, cached_input_tokens: 49668, output_tokens: 6543 });
    });
});
