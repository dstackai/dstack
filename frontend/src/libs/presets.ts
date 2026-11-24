/**
 * Formats a token count the way the CLI does: exact binary multiples keep
 * binary names (32768 is "32K"), anything else rounds as decimal (1500 is
 * "1.5K").
 */
export const formatTokenCount = (value: number): string => {
    for (const [divisor, suffix] of [
        [1024 * 1024, 'M'],
        [1024, 'K'],
    ] as const) {
        if (value >= divisor && value % divisor === 0) {
            return `${value / divisor}${suffix}`;
        }
    }

    if (value >= 999950) {
        return `${trimZero((value / 1_000_000).toFixed(1))}M`;
    }

    if (value >= 1000) {
        return `${trimZero((value / 1000).toFixed(1))}K`;
    }

    return String(value);
};

/** As the CLI prints a sweep: one value when they agree, otherwise `min..max`. */
export const formatTokenRange = (values: number[]): string => {
    const low = Math.min(...values);
    const high = Math.max(...values);
    return low === high ? formatTokenCount(low) : `${formatTokenCount(low)}..${formatTokenCount(high)}`;
};

const trimZero = (value: string): string => (value.endsWith('.0') ? value.slice(0, -2) : value);

/** As the CLI prints durations: 999.6 reads as 1s rather than 1000ms. */
const formatDurationMs = (value: number): string => (value < 999.5 ? `${round(value)}ms` : `${round(value / 1000)}s`);

const round = (value: number): string => String(Math.round(value * 100) / 100);

/**
 * Request counts, wall time, and token totals say nothing about how the preset
 * performs: the totals are the workload multiplied by the request count, which
 * the constraints already state.
 */
const HIDDEN_METRICS = new Set([
    'successful_requests',
    'failed_requests',
    'duration_seconds',
    'total_input_tokens',
    'total_output_tokens',
]);

const METRIC_LABELS: Record<string, string> = {
    output_tok_per_s: 'tok/s',
    per_user_tok_per_s: 'tok/s/user',
    total_input_tokens: 'Input tokens',
    total_output_tokens: 'Output tokens',
    ttft_ms: 'TTFT',
    tpot_ms: 'TPOT',
};

/** The tab a metric is shown under. A metric not listed here gets a tab of its own. */
const METRIC_GROUPS: Record<string, string> = {
    output_tok_per_s: 'tok/s',
    per_user_tok_per_s: 'tok/s',
    ttft_ms: 'TTFT',
    tpot_ms: 'TPOT',
};

const TOKEN_COUNT_METRICS = new Set(['total_input_tokens', 'total_output_tokens']);

export type BenchmarkChart = {
    group: string;
    title: string;
    formatValue: (value: number) => string;
    data: { x: string; y: number }[];
};

const getMetricFormatter = (key: string): ((value: number) => string) => {
    if (TOKEN_COUNT_METRICS.has(key)) return formatTokenCount;
    if (key.endsWith('_ms')) return formatDurationMs;
    return round;
};

export const sortResults = (results: IPresetResult[]): IPresetResult[] =>
    [...results].sort((a, b) => a.concurrency - b.concurrency);

/**
 * One chart per metric worth showing, each with a value per concurrency. A
 * metric measured as a distribution becomes one chart per statistic. A
 * concurrency without a benchmark has no point.
 */
export const getBenchmarkCharts = (results: IPresetResult[]): BenchmarkChart[] => {
    const charts = new Map<string, BenchmarkChart>();

    const addPoint = (title: string, key: string, concurrency: number, value: unknown) => {
        if (typeof value !== 'number') return;
        if (!charts.has(title)) {
            const group = METRIC_GROUPS[key] ?? METRIC_LABELS[key] ?? key;
            charts.set(title, { group, title, formatValue: getMetricFormatter(key), data: [] });
        }
        charts.get(title)?.data.push({ x: String(concurrency), y: value });
    };

    sortResults(results).forEach(({ concurrency, benchmark }) => {
        Object.entries(benchmark?.metrics ?? {}).forEach(([key, value]) => {
            if (HIDDEN_METRICS.has(key)) return;
            const label = METRIC_LABELS[key] ?? key;

            if (value && typeof value === 'object') {
                Object.entries(value as HashMap).forEach(([statistic, statisticValue]) =>
                    addPoint(`${label} ${statistic}`, key, concurrency, statisticValue),
                );
                return;
            }

            addPoint(label, key, concurrency, value);
        });
    });

    return Array.from(charts.values());
};
