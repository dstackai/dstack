import { formatTokenCount, getMetricFormatter } from 'libs/presets';

export type BenchmarkChart = {
    group: string;
    title: string;
    formatValue: (value: number) => string;
    data: { x: string; y: number }[];
};

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

/** The x axis: every concurrency of the sweep, in ascending order. */
export const getConcurrencies = (results: IPresetResult[]): string[] =>
    sortResults(results).map(({ concurrency }) => String(concurrency));

/**
 * One chart per metric worth showing, each with a value per concurrency, and
 * one for the context length. A metric measured as a distribution becomes one
 * chart per statistic. A concurrency without a benchmark has no point.
 */
export const getBenchmarkCharts = (results: IPresetResult[], contextLengthLabel: string): BenchmarkChart[] => {
    const charts = new Map<string, BenchmarkChart>();
    const sorted = sortResults(results);

    const addPoint = (title: string, key: string, concurrency: number, value: unknown) => {
        if (typeof value !== 'number') return;
        if (!charts.has(title)) {
            const group = METRIC_GROUPS[key] ?? METRIC_LABELS[key] ?? key;
            charts.set(title, { group, title, formatValue: getMetricFormatter(key), data: [] });
        }
        charts.get(title)?.data.push({ x: String(concurrency), y: value });
    };

    sorted.forEach(({ concurrency, benchmark }) => {
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

    const contextLengthChart: BenchmarkChart = {
        group: contextLengthLabel,
        title: contextLengthLabel,
        formatValue: formatTokenCount,
        data: sorted.flatMap(({ concurrency, context_length }) =>
            typeof context_length === 'number' ? [{ x: String(concurrency), y: context_length }] : [],
        ),
    };

    return [...Array.from(charts.values()), contextLengthChart];
};

/** The tabs, in the order their first chart appears. */
export const getChartGroups = (charts: BenchmarkChart[]): string[] => Array.from(new Set(charts.map(({ group }) => group)));

const sortResults = (results: IPresetResult[]): IPresetResult[] => [...results].sort((a, b) => a.concurrency - b.concurrency);
