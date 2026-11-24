import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { useGetPresetQuery } from 'services/preset';

import { getBenchmarkCharts, getChartGroups, getConcurrencies } from './helpers';

export const useBenchmarkCharts = (params: { project_name: string; id: string }) => {
    const { t } = useTranslation();
    const { data, isLoading } = useGetPresetQuery(params);

    const concurrencies = useMemo(() => getConcurrencies(data?.spec.preset.result ?? []), [data]);

    const charts = useMemo(() => getBenchmarkCharts(data?.spec.preset.result ?? [], t('presets.context_length')), [data, t]);

    const groups = useMemo(() => getChartGroups(charts), [charts]);

    return { isLoading: isLoading || !data, concurrencies, charts, groups };
};
