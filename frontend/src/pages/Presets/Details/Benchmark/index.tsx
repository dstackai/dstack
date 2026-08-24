import React, { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Box, ColumnLayout, Container, Header, Loader } from 'components';

import { formatTokenCount, getBenchmarkMetrics } from 'libs/presets';
import { useGetPresetQuery } from 'services/preset';

export const PresetBenchmark: FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramPresetId = params.presetId ?? '';

    const { data, isLoading } = useGetPresetQuery({
        project_name: paramProjectName,
        id: paramPresetId,
    });

    if (isLoading || !data)
        return (
            <Container>
                <Loader />
            </Container>
        );

    const metrics = getBenchmarkMetrics(data.spec.preset.benchmark.metrics as HashMap);

    return (
        <Container header={<Header variant="h2">{t('presets.benchmark')}</Header>}>
            <ColumnLayout columns={4} variant="text-grid">
                <div>
                    <Box variant="awsui-key-label">{t('presets.context_length')}</Box>
                    <div>{formatTokenCount(data.spec.preset.context_length)}</div>
                </div>
                <div>
                    <Box variant="awsui-key-label">{t('presets.concurrency')}</Box>
                    <div>{String((data.spec.preset.benchmark.workload as HashMap)?.concurrency)}</div>
                </div>
                {metrics.map(({ label, value }) => (
                    <div key={label}>
                        <Box variant="awsui-key-label">{label}</Box>
                        <div>{value}</div>
                    </div>
                ))}
            </ColumnLayout>
        </Container>
    );
};
