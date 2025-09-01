import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Cards, Header, Link, PropertyFilter, SelectCSD, StatusIndicator } from 'components';

import { useCollection } from 'hooks';
import { useGetGpusListQuery } from 'services/gpu';

import { useEmptyMessages } from './hooks/useEmptyMessages';
import { useFilters } from './hooks/useFilters';
import { convertMiBToGB, rangeToObject, renderRange, round } from './helpers';

import styles from './styles.module.scss';

const gpusFilterOption = { label: 'GPU', value: 'gpu' };

const getRequestParams = ({
    project_name,
    gpu_name,
    backend,
    gpu_count,
    gpu_memory,
    spot_policy,
}: {
    project_name: string;
    gpu_name?: string[];
    backend?: string[];
    gpu_count?: string;
    gpu_memory?: string;
    spot_policy?: TSpot;
}): TGpusListQueryParams => {
    const gpuCountMinMax = rangeToObject(gpu_count ?? '');
    const gpuMemoryMinMax = rangeToObject(gpu_memory ?? '');

    return {
        project_name: project_name,
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
                    // cpu: { min: 2 },
                    // memory: { min: 8.0 },
                    // disk: { size: { min: 100.0 } },
                    gpu: {
                        ...(gpu_name?.length ? { name: gpu_name } : {}),
                        ...(gpuCountMinMax ? { count: gpuCountMinMax } : {}),
                        ...(gpuMemoryMinMax ? { memory: gpuMemoryMinMax } : {}),
                    },
                },
                spot_policy,
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
    const [requestParams, setRequestParams] = useState<TGpusListQueryParams | undefined>();

    const { data, isLoading, isFetching } = useGetGpusListQuery(
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-expect-error
        requestParams,
        {
            skip: !requestParams || !requestParams['project_name'],
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

    useEffect(() => {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-expect-error
        setRequestParams(getRequestParams(filteringRequestParams));
    }, [JSON.stringify(filteringRequestParams)]);

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        clearFilter,
        projectNameSelected: Boolean(requestParams?.['project_name']),
    });

    const { items, collectionProps } = useCollection(requestParams?.['project_name'] ? (data?.gpus ?? []) : [], {
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
                header: (gpu) => <Link>{gpu.name}</Link>,
                sections: [
                    {
                        id: 'memory_mib',
                        header: t('offer.memory_mib'),
                        content: (gpu) => `${round(convertMiBToGB(gpu.memory_mib))}GB`,
                        width: 50,
                    },
                    {
                        id: 'price',
                        header: t('offer.price'),
                        content: (gpu) => <span className={styles.greenText}>{renderRange(gpu.price) ?? '-'}</span>,
                        width: 50,
                    },
                    {
                        id: 'count',
                        header: t('offer.count'),
                        content: (gpu) => renderRange(gpu.count) ?? '-',
                        width: 50,
                    },
                    {
                        id: 'backends',
                        header: t('offer.backend_plural'),
                        content: (gpu) => gpu.backends?.join(', ') ?? '-',
                        width: 50,
                    },
                    // {
                    //     id: 'region',
                    //     header: t('offer.region'),
                    //     content: (gpu) => gpu.region ?? gpu.regions?.join(', ') ?? '-',
                    //     width: 50,
                    // },
                    {
                        id: 'spot',
                        header: t('offer.spot'),
                        content: (gpu) => gpu.spot.join(', ') ?? '-',
                        width: 50,
                    },
                    {
                        id: 'availability',
                        content: (gpu) => {
                            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                            // @ts-expect-error
                            if (gpu.availability === 'not_available') {
                                return <StatusIndicator type="warning">Not Available</StatusIndicator>;
                            }
                        },
                        width: 50,
                    },
                ],
            }}
            loading={isLoading || isFetching}
            loadingText={t('common.loading')}
            stickyHeader={true}
            header={<Header variant="awsui-h1-sticky">{t('offer.title')}</Header>}
            variant="full-page"
            filter={
                <div className={styles.selectFilters}>
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

                    <div className={styles.filterField}>
                        <SelectCSD
                            inlineLabelText={t('offer.groupBy')}
                            options={[gpusFilterOption]}
                            selectedOption={gpusFilterOption}
                            expandToViewport={true}
                            disabled
                        />
                    </div>
                </div>
            }
        />
    );
};
