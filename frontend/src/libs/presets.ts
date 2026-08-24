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
    output_tok_per_s: 'TPS',
    per_user_tok_per_s: 'TPS/user',
    total_input_tokens: 'Input tokens',
    total_output_tokens: 'Output tokens',
    ttft_ms: 'TTFT',
    tpot_ms: 'TPOT',
};

const TOKEN_COUNT_METRICS = new Set(['total_input_tokens', 'total_output_tokens']);

export type BenchmarkMetric = { label: string; value: string };

const formatMetricValue = (key: string, value: number): string => {
    if (TOKEN_COUNT_METRICS.has(key)) return formatTokenCount(value);
    if (key.endsWith('_ms')) return formatDurationMs(value);
    return round(value);
};

/**
 * The metrics worth showing, flattened: a metric measured as a distribution
 * becomes one entry per statistic.
 */
export const getBenchmarkMetrics = (metrics: HashMap): BenchmarkMetric[] => {
    const entries: BenchmarkMetric[] = [];

    Object.entries(metrics ?? {}).forEach(([key, value]) => {
        if (HIDDEN_METRICS.has(key)) return;
        const label = METRIC_LABELS[key] ?? key;

        if (typeof value === 'number') {
            entries.push({ label, value: formatMetricValue(key, value) });
            return;
        }

        if (value && typeof value === 'object') {
            Object.entries(value as HashMap).forEach(([statistic, statisticValue]) => {
                if (typeof statisticValue !== 'number') return;
                entries.push({
                    label: `${label} ${statistic}`,
                    value: formatMetricValue(key, statisticValue),
                });
            });
        }
    });

    return entries;
};
