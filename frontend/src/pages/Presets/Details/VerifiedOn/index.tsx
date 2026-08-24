import React, { FC, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Container, Header, Loader, TreeView } from 'components';

import { useGetPresetQuery } from 'services/preset';

type VerifiedOnItem = {
    id: string;
    content: string;
    children?: VerifiedOnItem[];
};

/** The resources of one replica, in the shape the CLI prints them. */
const formatResources = (replicas: HashMap): string => {
    const parts: string[] = [];
    const range = (value: unknown, unit = ''): string | null => {
        if (value === null || value === undefined) return null;
        if (typeof value === 'object') {
            const { min, max } = value as { min?: number; max?: number };
            if (min === undefined && max === undefined) return null;
            return min === max || max === undefined ? `${min}${unit}` : `${min}..${max}${unit}`;
        }
        return `${String(value)}${unit}`;
    };

    // `cpu` is not a bare range like `memory`: it carries the architecture and
    // the core count, and the CLI prints them as `cpu=<arch>:<count>`.
    const cpu = replicas.cpu as HashMap | undefined;
    if (cpu) {
        const cores = range(cpu.count);
        const cpuParts = [cpu.arch, cores].filter(Boolean);
        if (cpuParts.length) parts.push(`cpu=${cpuParts.join(':')}`);
    }
    const memory = range(replicas.memory, 'GB');
    if (memory) parts.push(`mem=${memory}`);
    const gpu = replicas.gpu as HashMap | undefined;
    if (gpu) {
        const names = Array.isArray(gpu.name) ? gpu.name.join(',') : gpu.name;
        const count = range(gpu.count);
        const gpuMemory = range(gpu.memory, 'GB');
        parts.push(`gpu=${[names, gpuMemory, count].filter(Boolean).join(':')}`);
    }
    const diskSize = range((replicas.disk as HashMap | undefined)?.size, 'GB');
    if (diskSize) parts.push(`disk=${diskSize}`);

    return parts.join(' ');
};

export const PresetVerifiedOn: FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramPresetId = params.presetId ?? '';

    const { data, isLoading } = useGetPresetQuery({
        project_name: paramProjectName,
        id: paramPresetId,
    });

    // Every group starts expanded: a preset has few of them, and the replicas
    // are the point of the tab.
    const groupNames = useMemo(() => (data?.spec.preset.verified_on ?? []).map(({ name }) => name), [data]);
    const [collapsedItems, setCollapsedItems] = useState<string[]>([]);
    const expandedItems = groupNames.filter((name) => !collapsedItems.includes(name));

    if (isLoading || !data)
        return (
            <Container>
                <Loader />
            </Container>
        );

    // A group was verified with a set of replicas, which is a tree, not a list.
    const items: VerifiedOnItem[] = data.spec.preset.verified_on.map((group) => ({
        id: group.name,
        content: t('presets.replica_group', { name: group.name }),
        children: group.replicas.map((replicas, index) => ({
            id: `${group.name}-${index}`,
            content: `${t('presets.replica', { index: index + 1 })}: ${formatResources(replicas)}`,
        })),
    }));

    return (
        <Container header={<Header variant="h2">{t('presets.verified_on')}</Header>}>
            <TreeView
                items={items}
                expandedItems={expandedItems}
                onItemToggle={({ detail }) =>
                    setCollapsedItems((currentItems) =>
                        detail.expanded ? currentItems.filter((itemId) => itemId !== detail.id) : [...currentItems, detail.id],
                    )
                }
                getItemId={(item) => item.id}
                getItemChildren={(item) => item.children}
                renderItem={(item) => ({ content: item.content })}
                i18nStrings={{
                    expandButtonLabel: () => 'Expand',
                    collapseButtonLabel: () => 'Collapse',
                }}
            />
        </Container>
    );
};
