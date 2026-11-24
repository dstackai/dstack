import React, { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Box, ColumnLayout, Container, Header, Loader } from 'components';

import { formatTokenCount, formatTokenRange } from 'libs/presets';
import { useGetPresetQuery } from 'services/preset';

export const PresetConstraints: FC = () => {
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

    // The conditions the benchmark holds for: the workload it measured and the
    // context the service was verified to serve.
    // The dataset and shared prefix are the same across concurrencies, so the
    // first benchmarked result stands for all of them. The measured token
    // averages can differ, so those show as ranges.
    const results = data.spec.preset.result;
    const workloads = results.flatMap(({ benchmark }) => (benchmark ? [benchmark.workload as HashMap] : []));
    const workload = workloads[0] ?? {};
    const dataset = workload.dataset as string | undefined;
    const inputTokens = workload.input_tokens as number;
    const sharedPrefix = (workload.shared_prefix_tokens as number) ?? 0;

    return (
        <Container header={<Header variant="h2">{t('presets.constraints')}</Header>}>
            <ColumnLayout columns={4} variant="text-grid">
                {dataset && (
                    <div>
                        <Box variant="awsui-key-label">{t('presets.dataset')}</Box>
                        <div>{dataset}</div>
                    </div>
                )}
                <div>
                    <Box variant="awsui-key-label">{t('presets.input_tokens')}</Box>
                    <div>{formatTokenRange(workloads.map((w) => w.input_tokens as number))}</div>
                </div>
                <div>
                    <Box variant="awsui-key-label">{t('presets.output_tokens')}</Box>
                    <div>{formatTokenRange(workloads.map((w) => w.output_tokens as number))}</div>
                </div>
                {sharedPrefix > 0 && (
                    <div>
                        <Box variant="awsui-key-label">{t('presets.shared_prefix')}</Box>
                        <div>
                            {formatTokenCount(sharedPrefix)} ({Math.round((100 * sharedPrefix) / inputTokens)}%)
                        </div>
                    </div>
                )}
            </ColumnLayout>
        </Container>
    );
};
