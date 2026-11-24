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

const TOKEN_COUNT_METRICS = new Set(['total_input_tokens', 'total_output_tokens']);

/** How a benchmark metric's values are printed, picked by the metric's name. */
export const getMetricFormatter = (key: string): ((value: number) => string) => {
    if (TOKEN_COUNT_METRICS.has(key)) return formatTokenCount;
    if (key.endsWith('_ms')) return formatDurationMs;
    return round;
};
