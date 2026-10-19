import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Badge from '@cloudscape-design/components/badge';
import { skipToken } from '@reduxjs/toolkit/query';

import { Alert, Button, Cards, CardsProps, MultiselectCSD, Popover, PropertyFilter, SpaceBetween, Toggle } from 'components';

import { useCollection } from 'hooks';
import { getServerError } from 'libs';
import { formatBackend } from 'libs/fleet';
import { useGetGpusListQuery, useGetOffersQuery } from 'services/gpu';

import { useEmptyMessages } from './hooks/useEmptyMessages';
import { useFilters, UseFiltersArgs } from './hooks/useFilters';
import {
    convertMiBToGB,
    formatGpuVendor,
    getCpuMemory,
    getOfferAvailability,
    OfferCard,
    rangeToObject,
    renderRange,
    renderRangeJSX,
    round,
    toCpuCard,
    toOfferCard,
} from './helpers';

import styles from './styles.module.scss';

export const getRequestParams = ({
    project_name,
    gpu_vendor,
    gpu_name,
    backend,
    fleet,
    gpu_count,
    gpu_memory,
    cpu_count,
    cpu_arch,
    memory,
    region,
    spot_policy,
    group_by,
}: {
    project_name: string;
    gpu_vendor?: string;
    gpu_name?: string[];
    backend?: string[];
    fleet?: string[];
    gpu_count?: string;
    gpu_memory?: string;
    cpu_count?: string;
    cpu_arch?: string;
    memory?: string;
    region?: string;
    spot_policy?: TSpot;
    group_by?: TGpuGroupBy[];
}): TGpusListQueryParams => {
    const gpuCountMinMax = rangeToObject(gpu_count ?? '');
    const gpuMemoryMinMax = rangeToObject(gpu_memory ?? '', { requireUnit: true });

    return {
        project_name,
        group_by,
        run_spec: {
            configuration: {
                nodes: 1,
                ports: [],
                commands: [':'],
                type: 'task',
                image: 'scratch',
                privileged: false,
                home_dir: '/root',
                env: {},
                resources: {
                    // Default to the same minimal CPU, memory and disk constraints as `dstack offer`.
                    cpu: {
                        count: (rangeToObject(cpu_count ?? '') as TRange | undefined) ?? { min: 1 },
                        ...(cpu_arch ? { arch: cpu_arch as 'x86' | 'arm' } : {}),
                    },
                    memory: (rangeToObject(memory ?? '', { requireUnit: true }) as TRange | undefined) ?? { min: 0.0 },
                    disk: null,
                    gpu: {
                        ...(gpu_vendor ? { vendor: gpu_vendor } : {}),
                        ...(gpu_name?.length ? { name: gpu_name } : {}),
                        count: gpuCountMinMax ? (gpuCountMinMax as unknown as TRange) : { min: 1 },
                        ...(gpuMemoryMinMax ? { memory: gpuMemoryMinMax as unknown as TRange } : {}),
                    },
                },
                spot_policy,
                volumes: [],
                files: [],
                setup: [],
                ...(backend?.length ? { backends: backend as TBackendType[] } : {}),
                ...(fleet?.length ? { fleets: fleet } : {}),
                ...(region ? { regions: [region] } : {}),
            },
            profile: { name: 'default', default: false },
            ssh_key_pub: '(dummy)',
        },
        // TODO: Add UI controls for full_offers and unallocated_resources for both grouped and individual offers.
        full_offers: true,
    };
};

type OfferListProps = Pick<
    CardsProps<OfferCard>,
    'variant' | 'header' | 'onSelectionChange' | 'selectedItems' | 'selectionType'
> & {
    permanentFilters?: UseFiltersArgs['permanentFilters'];
    defaultFilters?: UseFiltersArgs['defaultFilters'];
    withSearchParams?: boolean;
    showFleetFilter?: boolean;
    allowUngrouped?: boolean;
    onChangeBackendFilter?: (backends: string[]) => void;
    onChangeFleetFilter?: (fleets: string[]) => void;
    /** An offer to select once matching resources load. */
    preselectedOffer?: {
        name?: string;
        memoryGb?: number;
        cpuCount?: string;
        cpuMemory?: string;
        cpuArch?: string | null;
        backend?: TBackendType;
        region?: string;
    };
    onPreselect?: (gpu: OfferCard) => void;
    onChangeFilters?: UseFiltersArgs['onChange'];
    /** Called with whether the project has no offers without custom filters. */
    onChangeNoOffers?: (noOffers: boolean) => void;
};

export const OfferList: React.FC<OfferListProps> = ({
    withSearchParams,
    showFleetFilter,
    allowUngrouped = false,
    onChangeBackendFilter,
    onChangeFleetFilter,
    permanentFilters,
    defaultFilters,
    preselectedOffer,
    onPreselect,
    onChangeFilters,
    onChangeNoOffers,
    ...props
}) => {
    const { t } = useTranslation();
    const [requestParams, setRequestParams] = useState<TGpusListQueryParams | undefined>();

    const groupedQuery = useGetGpusListQuery(requestParams ?? skipToken, {
        skip: !requestParams || !requestParams['project_name'] || !requestParams['group_by']?.length,
        refetchOnMountOrArgChange: true,
    });
    const offersQuery = useGetOffersQuery(requestParams ?? skipToken, {
        skip: !allowUngrouped || !requestParams?.project_name || !!requestParams.group_by?.length,
        refetchOnMountOrArgChange: true,
    });
    const individualCards = useMemo(() => (offersQuery.currentData?.offers ?? []).map(toOfferCard), [offersQuery.currentData]);

    const {
        filteringRequestParams,
        clearFilter,
        hasCustomFilters,
        propertyFilterRef,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        groupBy,
        groupByOptions,
        onChangeGroupBy,
        gpuEnabled,
        onChangeGpu,
        canAutoSelectCpu,
        filteringStatusType,
        handleLoadItems,
    } = useFilters({
        gpus: requestParams?.group_by?.length
            ? (groupedQuery.currentData?.cpus ?? groupedQuery.currentData?.gpus ?? [])
            : individualCards,
        withSearchParams,
        showFleetFilter,
        allowUngrouped,
        permanentFilters,
        defaultFilters,
        onChange: onChangeFilters,
    });

    const ungrouped = allowUngrouped && !groupBy.length;
    const { error, isError, isLoading, isFetching } = ungrouped ? offersQuery : groupedQuery;

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
        const backend = filteringRequestParams.backend;
        const backendValues = backend
            ? (Array.isArray(backend) ? backend : [backend]).filter((value): value is string => typeof value === 'string')
            : [];
        onChangeBackendFilter?.(backendValues);
    }, [filteringRequestParams.backend]);

    useEffect(() => {
        const fleet = filteringRequestParams.fleet;
        const fleetValues = fleet
            ? (Array.isArray(fleet) ? fleet : [fleet]).filter((value): value is string => typeof value === 'string')
            : [];
        onChangeFleetFilter?.(fleetValues);
    }, [filteringRequestParams.fleet]);

    const { renderEmptyMessage, renderNoMatchMessage } = useEmptyMessages({
        clearFilter,
        projectName: requestParams?.['project_name'],
        groupBySelected: !ungrouped && Boolean(requestParams?.['group_by']?.length),
        ungrouped,
        hasCustomFilters,
        isFleet: Boolean(permanentFilters?.fleet),
    });

    const gpus = useMemo(
        () =>
            gpuEnabled
                ? (groupedQuery.currentData?.gpus ?? []).map((gpu) => ({ ...gpu, price: gpu.offer_price ?? gpu.price }))
                : (groupedQuery.currentData?.cpus ?? []).map(toCpuCard),
        [groupedQuery.currentData, gpuEnabled],
    );

    const noOffers =
        !!requestParams?.project_name &&
        (ungrouped || !!requestParams?.group_by?.length) &&
        !isLoading &&
        !isFetching &&
        !isError &&
        !hasCustomFilters &&
        (ungrouped ? offersQuery.currentData?.offers.length === 0 : gpus.length === 0);

    useEffect(() => {
        onChangeNoOffers?.(noOffers);
        if (noOffers && gpuEnabled && canAutoSelectCpu) {
            onChangeGpu(false);
        }
    }, [noOffers]);

    const cards = useMemo<OfferCard[]>(() => (ungrouped ? individualCards : gpus), [ungrouped, individualCards, gpus]);

    const isPreselected = useRef(false);

    useEffect(() => {
        if (!preselectedOffer || isPreselected.current) {
            return;
        }

        const gpu = cards.find(
            (offer) =>
                (preselectedOffer.cpuCount
                    ? !!offer.cpu && renderRange(offer.count) === preselectedOffer.cpuCount
                    : offer.name === preselectedOffer.name) &&
                (!preselectedOffer.cpuMemory || getCpuMemory(offer) === preselectedOffer.cpuMemory) &&
                (!preselectedOffer.cpuArch || offer.cpu?.cpu_arch === preselectedOffer.cpuArch) &&
                (!preselectedOffer.backend || offer.backend === preselectedOffer.backend) &&
                (!preselectedOffer.region || offer.region === preselectedOffer.region) &&
                (preselectedOffer.memoryGb === undefined || convertMiBToGB(offer.memory_mib) === preselectedOffer.memoryGb),
        );

        if (gpu) {
            isPreselected.current = true;
            onPreselect?.(gpu);
        }
    }, [cards]);

    const { items, collectionProps } = useCollection(
        requestParams?.project_name && (ungrouped || requestParams.group_by?.length) ? cards : [],
        {
            filtering: {
                empty: renderEmptyMessage(),
                noMatch: renderNoMatchMessage(),
            },
            selection: {},
        },
    );

    const sections: CardsProps.CardDefinition<OfferCard>['sections'] = [
        {
            id: 'resources',
            content: (gpu) => {
                const availability = getOfferAvailability(gpu.availability);
                const label = availability && (
                    <span className={styles.greyText}>{t(`offer.availability_${availability}`)}</span>
                );
                return (
                    <div className={styles.cardContent}>
                        <div>
                            {gpu.cpu?.memory_range
                                ? renderRange({
                                      min: round(convertMiBToGB(gpu.cpu.memory_range.min)),
                                      max: round(convertMiBToGB(gpu.cpu.memory_range.max)),
                                  })
                                : round(convertMiBToGB(gpu.memory_mib))}
                            GB <span className={styles.greyText}>{gpu.cpu ? 'RAM' : 'VRAM'}</span>
                        </div>
                        <span className={styles.greenText}>${renderRangeJSX(gpu.price) ?? '-'}</span>
                        <div>
                            {gpu.backend ? formatBackend(gpu.backend) : (gpu.backends?.map(formatBackend).join(', ') ?? '-')}
                        </div>
                        <div>{gpu.spot.join(', ') || '-'}</div>
                        {ungrouped && gpu.region && <div>{gpu.region}</div>}
                        {label &&
                            (gpu.availability.length === 1 ? (
                                label
                            ) : (
                                <Popover
                                    dismissButton={false}
                                    position="top"
                                    size="small"
                                    content={gpu.availability.map((a) => t(`offer.availability_${a}`)).join(', ')}
                                >
                                    {label}
                                </Popover>
                            ))}
                    </div>
                );
            },
        },
    ];

    return (
        <>
            {isError && (
                <Alert type="error" header="Error">
                    {t('common.server_error', { error: getServerError(error) })}
                </Alert>
            )}

            <Cards<OfferCard>
                {...collectionProps}
                {...props}
                entireCardClickable
                cardsPerRow={[
                    { cards: 1 },
                    { minWidth: 580, cards: 2 },
                    { minWidth: 900, cards: 3 },
                    { minWidth: 1200, cards: 4 },
                ]}
                items={items}
                cardDefinition={{
                    header: (gpu) => {
                        const architectures = gpu.cpu?.architectures ?? (gpu.cpu?.cpu_arch ? [gpu.cpu.cpu_arch] : []);
                        const badge = gpu.cpu
                            ? architectures
                                  .map((arch) => (arch === 'x86' ? 'x86_64' : arch === 'arm' ? 'arm64' : arch))
                                  .join(', ')
                            : formatGpuVendor(gpu.vendor);
                        return (
                            <SpaceBetween direction="horizontal" size="xs">
                                <span>{`${gpu.cpu ? 'CPU' : gpu.name}:${renderRange(gpu.count)}`}</span>
                                {badge && <Badge color="grey">{badge}</Badge>}
                            </SpaceBetween>
                        );
                    },
                    sections,
                }}
                loading={isLoading || isFetching}
                loadingText={t('common.loading')}
                stickyHeader={true}
                filter={
                    <div className={styles.selectFilters}>
                        <div className={styles.propertyFilter}>
                            <PropertyFilter
                                ref={propertyFilterRef}
                                disabled={isLoading || isFetching}
                                query={propertyFilterQuery}
                                onChange={onChangePropertyFilter}
                                customFilterActions={
                                    <Button
                                        variant="link"
                                        formAction="none"
                                        onClick={clearFilter}
                                        disabled={isLoading || isFetching}
                                    >
                                        {t('common.clearFilter')}
                                    </Button>
                                }
                                expandToViewport
                                hideOperations
                                i18nStrings={{
                                    clearFiltersText: t('common.clearFilter'),
                                    filteringAriaLabel: t('offer.filter_property_placeholder'),
                                    filteringPlaceholder: t('offer.filter_property_placeholder'),
                                    operationAndText: 'and',
                                    enteredTextLabel: (value) => `Use: ${value}`,
                                }}
                                filteringOptions={filteringOptions}
                                filteringProperties={filteringProperties}
                                filteringStatusType={filteringStatusType}
                                onLoadItems={handleLoadItems}
                            />
                        </div>

                        {allowUngrouped && (
                            <div className={styles.gpuToggle}>
                                <Toggle
                                    checked={gpuEnabled}
                                    onChange={({ detail }) => onChangeGpu(detail.checked)}
                                    disabled={isLoading || isFetching}
                                >
                                    GPU
                                </Toggle>
                            </div>
                        )}

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
            {ungrouped &&
                offersQuery.currentData &&
                offersQuery.currentData.total_offers > offersQuery.currentData.offers.length && (
                    <Alert type="info">
                        {t('offer.truncated', {
                            shown: offersQuery.currentData.offers.length,
                            total: offersQuery.currentData.total_offers,
                        })}
                    </Alert>
                )}
        </>
    );
};
