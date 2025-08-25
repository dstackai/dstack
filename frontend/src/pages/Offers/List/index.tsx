import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import type { SelectCSDProps } from 'components';
import { Box, Cards, Header, PropertyFilter, SelectCSD } from 'components';

import { useCollection } from 'hooks';
import { useProjectFilter } from 'hooks/useProjectFilter';
import { useGetGpusListQuery } from 'services/gpu';

import { useEmptyMessages } from './hooks/useEmptyMessages';
import { useFilters } from './hooks/useFilters';
import { bytesFormatter } from '../../Runs/Details/Jobs/Metrics/helpers';
import { renderRange, stringRangeToObject } from './helpers';

import styles from './styles.module.scss';

const getRequestParams = ({
    gpu_name,
    backend,
    gpu_count,
    gpu_memory,
}: {
    gpu_name?: string[];
    backend?: string[];
    gpu_count?: string;
    gpu_memory?: string;
}): Omit<TGpusListQueryParams, 'project_name'> => {
    const gpuCountMinMax = stringRangeToObject(gpu_count ?? '');
    const gpuMemoryMinMax = stringRangeToObject(gpu_memory ?? '');

    return {
        run_spec: {
            configuration: {
                nodes: 1,
                ports: [],
                commands: [':'],
                type: 'task',
                privileged: false,
                home_dir: '/root',
                env: {},
                resources: {
                    cpu: { min: 2 },
                    memory: { min: 8.0 },
                    disk: { size: { min: 100.0 } },
                    gpu: {
                        ...(gpu_name?.length ? { name: gpu_name } : {}),
                        ...(gpuCountMinMax ? { count: gpuCountMinMax } : {}),
                        ...(gpuMemoryMinMax ? { memory: gpuMemoryMinMax } : {}),
                    },
                },
                volumes: [],
                files: [],
                setup: [],
                ...(backend?.length ? { backends: backend } : {}),
            },
            profile: { name: 'default', default: false },
            ssh_key_pub: '(dummy)',
        },
    };
};

export const OfferList = () => {
    const { t } = useTranslation();
    const [requestParams, setRequestParams] = useState<Omit<TGpusListQueryParams, 'project_name'> | undefined>();
    const [searchParams, setSearchParams] = useSearchParams();

    const { projectOptions, selectedProject, setSelectedProject } = useProjectFilter({
        localStorePrefix: 'offers-list-projects',
    });

    console.log({ requestParams });
    const { data, isLoading, isFetching } = useGetGpusListQuery(
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-expect-error
        {
            project_name: selectedProject?.value ?? '',
            ...requestParams,
        },
        {
            skip: !selectedProject || !requestParams,
        },
    );

    const {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
    } = useFilters({ gpus: data?.gpus ?? [] });

    console.log({ filteringRequestParams });

    useEffect(() => {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-expect-error
        setRequestParams(getRequestParams(filteringRequestParams));
    }, [JSON.stringify(filteringRequestParams)]);

    const onChangeProjectName = (project: SelectCSDProps.Option) => {
        setSelectedProject(project);
        setSearchParams({ project_name: project.value ?? '' });
    };

    useEffect(() => {
        if (!selectedProject && projectOptions?.length) {
            const searchParamProjectName = searchParams.get('project_name');

            onChangeProjectName(projectOptions.find((p) => p.value === searchParamProjectName) ?? projectOptions[0]);
        }
    }, [projectOptions]);

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({ clearFilter });

    const { items, collectionProps } = useCollection(data?.gpus ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(),
        },
        selection: {},
    });

    return (
        <Cards
            {...collectionProps}
            items={items}
            cardDefinition={{
                header: (gpu) => gpu.name,
                sections: [
                    {
                        id: 'backend',
                        header: t('offer.backend'),
                        content: (gpu) => gpu.backend ?? gpu.backends?.join(', ') ?? '-',
                        width: 50,
                    },
                    {
                        id: 'region',
                        header: t('offer.region'),
                        content: (gpu) => gpu.region ?? gpu.regions?.join(', ') ?? '-',
                        width: 50,
                    },
                    {
                        id: 'count',
                        header: t('offer.count'),
                        content: (gpu) => renderRange(gpu.count) ?? '-',
                        width: 50,
                    },
                    {
                        id: 'price',
                        header: t('offer.price'),
                        content: (gpu) => renderRange(gpu.price) ?? '-',
                        width: 50,
                    },
                    {
                        id: 'memory_mib',
                        header: t('offer.memory_mib'),
                        content: (gpu) => bytesFormatter(gpu.memory_mib),
                        width: 50,
                    },
                ],
            }}
            loading={isLoading || isFetching}
            loadingText={t('common.loading')}
            stickyHeader={true}
            header={<Header variant="awsui-h1-sticky">{t('offer.title')}</Header>}
            filter={
                <div className={styles.selectFilters}>
                    <div className={styles.filterField}>
                        <Box>{t('offer.project_name_label')}:</Box>
                        <div className={styles.selectFilter}>
                            <SelectCSD
                                disabled={isLoading || isFetching}
                                options={projectOptions}
                                selectedOption={selectedProject}
                                onChange={({ detail: { selectedOption } }) => onChangeProjectName(selectedOption)}
                            />
                        </div>
                    </div>

                    <div className={styles.propertyFilter}>
                        <PropertyFilter
                            disabled={isLoading || isFetching}
                            query={propertyFilterQuery}
                            onChange={onChangePropertyFilter}
                            expandToViewport
                            hideOperations
                            i18nStrings={{
                                clearFiltersText: t('common.clearFilter'),
                                filteringAriaLabel: t('offer.filter_property_placeholder'),
                                filteringPlaceholder: t('offer.filter_property_placeholder'),
                                operationAndText: 'and',
                            }}
                            filteringOptions={filteringOptions}
                            filteringProperties={filteringProperties}
                        />
                    </div>
                </div>
            }
        />
    );
};
