import React, { FC, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { BarChart, Box, Container, Header, Loader, SelectCSD, Tabs } from 'components';

import { useBenchmarkCharts } from './useBenchmarkCharts';

export const PresetBenchmark: FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramPresetId = params.presetId ?? '';
    const [activeGroup, setActiveGroup] = useState<string | null>(null);
    // Each tab remembers the metric last picked in it.
    const [metricByGroup, setMetricByGroup] = useState<Record<string, string>>({});

    const { isLoading, concurrencies, charts, groups } = useBenchmarkCharts({
        project_name: paramProjectName,
        id: paramPresetId,
    });

    if (isLoading)
        return (
            <Container>
                <Loader />
            </Container>
        );

    const group = activeGroup ?? groups[0];
    const groupCharts = charts.filter((chart) => chart.group === group);
    const chart = groupCharts.find(({ title }) => title === metricByGroup[group]) ?? groupCharts[0];

    // Only the open tab's chart is drawn, so the others carry no content.
    const tabs = groups.map((id) => ({
        id,
        label: id,
        content: id === group && (
            <BarChart
                series={[{ title: chart.title, type: 'bar', data: chart.data, valueFormatter: chart.formatValue }]}
                xDomain={concurrencies}
                xScaleType="categorical"
                xTitle={t('presets.concurrency')}
                i18nStrings={{ yTickFormatter: chart.formatValue }}
                ariaLabel={chart.title}
                height={300}
                hideFilter
                hideLegend
                empty={<Box textAlign="center">{t('presets.no_benchmark_data')}</Box>}
            />
        ),
    }));

    return (
        <Container header={<Header variant="h2">{t('presets.benchmark')}</Header>}>
            <Tabs
                tabs={tabs}
                activeTabId={group}
                onChange={({ detail }) => setActiveGroup(detail.activeTabId)}
                // A tab with a single metric has nothing to pick.
                actions={
                    groupCharts.length > 1 && (
                        <SelectCSD
                            selectedOption={{ label: chart.title, value: chart.title }}
                            options={groupCharts.map(({ title }) => ({ label: title, value: title }))}
                            onChange={({ detail }) =>
                                setMetricByGroup((current) => ({
                                    ...current,
                                    [group]: detail.selectedOption.value ?? chart.title,
                                }))
                            }
                            ariaLabel={t('presets.metric')}
                        />
                    )
                }
            />
        </Container>
    );
};
