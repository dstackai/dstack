import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Cards, CardsProps, MultiselectCSD, PropertyFilter, StatusIndicator } from 'components';

import { useCollection } from 'hooks';
import { useGetGpusListQuery } from 'services/gpu';

import { useEmptyMessages } from './hooks/useEmptyMessages';
import { useFilters } from './hooks/useFilters';
import { convertMiBToGB, rangeToObject, renderRange, renderRangeJSX, round } from './helpers';

import styles from './styles.module.scss';

const getRequestParams = ({
    project_name,
    gpu_name,
    backend,
    gpu_count,
    gpu_memory,
    spot_policy,
    group_by,
}: {
    project_name: string;
    gpu_name?: string[];
    backend?: string[];
    gpu_count?: string;
    gpu_memory?: string;
    spot_policy?: TSpot;
    group_by?: TGpuGroupBy[];
}): TGpusListQueryParams => {
    const gpuCountMinMax = rangeToObject(gpu_count ?? '');
    const gpuMemoryMinMax = rangeToObject(gpu_memory ?? '');

    return {
        project_name,
        group_by,
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

type OfferListProps = Pick<CardsProps, 'variant' | 'header' | 'onSelectionChange' | 'selectedItems' | 'selectionType'> & {
    withSearchParams?: boolean;
    onChangeProjectName?: (value: string) => void;
};

export const OfferList: React.FC<OfferListProps> = ({ withSearchParams, onChangeProjectName, ...props }) => {
    const { t } = useTranslation();
    const [requestParams, setRequestParams] = useState<TGpusListQueryParams | undefined>();
    const { data, isLoading, isFetching } = useGetGpusListQuery(
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-expect-error
        requestParams,
        {
            skip: !requestParams || !requestParams['project_name'] || !requestParams['group_by']?.length,
        },
    );

    const {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        groupBy,
        groupByOptions,
        onChangeGroupBy,
    } = useFilters({ gpus: data?.gpus ?? [], withSearchParams });

    useEffect(() => {
        setRequestParams(
            getRequestParams({
                ...filteringRequestParams,
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                group_by: groupBy.map(({ value }) => value),
            }),
        );
    }, [JSON.stringify(filteringRequestParams), groupBy]);

    useEffect(() => {
        onChangeProjectName?.(filteringRequestParams.project_name ?? '');
    }, [filteringRequestParams.project_name]);

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        clearFilter,
        projectNameSelected: Boolean(requestParams?.['project_name']),
        groupBySelected: Boolean(requestParams?.['group_by']?.length),
    });

    const { items, collectionProps } = useCollection(
        requestParams?.['project_name'] && requestParams?.['group_by']?.length ? (data?.gpus ?? []) : [],
        {
            filtering: {
                empty: renderEmptyMessage(),
                noMatch: renderNoMatchMessage(),
            },
            selection: {},
        },
    );

    const groupByBackend = groupBy.some(({ value }) => value === 'backend');

    const sections = [
        {
            id: 'memory_mib',
            // header: t('offer.memory_mib'),
            content: (gpu: IGpu) => (
                <div>
                    {round(convertMiBToGB(gpu.memory_mib))}GB
                    <span className={styles.greyText}>:</span>
                    {renderRange(gpu.count)}
                </div>
            ),
            width: 50,
        },
        {
            id: 'price',
            // header: t('offer.price'),
            content: (gpu: IGpu) => <span className={styles.greenText}>${renderRangeJSX(gpu.price) ?? '-'}</span>,
            width: 50,
        },
        // {
        //     id: 'count',
        //     header: t('offer.count'),
        //     content: (gpu: IGpu) => renderRange(gpu.count) ?? '-',
        //     width: 50,
        // },
        !groupByBackend && {
            id: 'backends',
            // header: t('offer.backend_plural'),
            content: (gpu: IGpu) => gpu.backends?.join(', ') ?? '-',
            width: 50,
        },
        groupByBackend && {
            id: 'backend',
            // header: t('offer.backend'),
            content: (gpu: IGpu) => gpu.backend ?? '-',
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
            // header: t('offer.spot'),
            content: (gpu: IGpu) => gpu.spot.join(', ') ?? '-',
            width: 50,
        },
        {
            id: 'availability',
            content: (gpu: IGpu) => {
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                if (gpu.availability === 'not_available') {
                    return <StatusIndicator type="warning">Not Available</StatusIndicator>;
                }
            },
            width: 50,
        },
    ].filter(Boolean) as CardsProps.CardDefinition<IGpu>['sections'];

    return (
        <Cards
            {...collectionProps}
            {...props}
            entireCardClickable
            items={items}
            cardDefinition={{
                header: (gpu) => gpu.name,
                sections,
            }}
            loading={isLoading || isFetching}
            loadingText={t('common.loading')}
            stickyHeader={true}
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
                        <MultiselectCSD
                            placeholder={t('offer.groupBy')}
                            onChange={onChangeGroupBy}
                            options={groupByOptions}
                            selectedOptions={groupBy}
                            expandToViewport={true}
                            disabled={isLoading || isFetching}
                        />
                    </div>
                </div>
            }
        />
    );
};
