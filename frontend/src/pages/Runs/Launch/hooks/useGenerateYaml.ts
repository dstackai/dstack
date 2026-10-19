import { useMemo } from 'react';
import jsYaml from 'js-yaml';

import { getOfferResources } from 'pages/Offers/List/helpers';
import type { UseFiltersArgs } from 'pages/Offers/List/hooks/useFilters';

import { IRunEnvironmentFormValues } from '../types';

export type UseGenerateYamlArgs = {
    formValues: IRunEnvironmentFormValues;
    configuration?: ITemplate['configuration'];
    envParam?: TTemplateParam;
    hasResourcesParam?: boolean;
    backends?: string[];
    fleets?: string[];
    filters?: UseFiltersArgs['defaultFilters'];
};

export const useGenerateYaml = ({
    formValues,
    configuration,
    envParam,
    hasResourcesParam,
    backends,
    fleets,
    filters,
}: UseGenerateYamlArgs) => {
    return useMemo(() => {
        const { name, ide, image, python, offer, repo_url, repo_path, working_dir, password } = formValues;
        const hasTemplateResources =
            configuration &&
            'resources' in configuration &&
            configuration.resources &&
            typeof configuration.resources === 'object'
                ? true
                : false;
        const baseResources =
            hasTemplateResources && configuration ? (configuration.resources as Record<string, unknown>) : undefined;
        const filterConfiguration =
            hasResourcesParam && filters ? getFilterConfiguration(filters, baseResources) : { resources: baseResources };

        const envEntries: string[] = [];
        if (envParam?.name && password) {
            envEntries.push(`${envParam.name}=${password}`);
        }
        if (configuration && 'env' in configuration) {
            envEntries.push(...(configuration['env'] as string[]));
        }

        return jsYaml.dump(
            {
                ...configuration,
                ...filterConfiguration,

                ...(name ? { name } : {}),
                ...(ide ? { ide } : {}),
                ...(image ? { image } : {}),
                ...(python ? { python } : {}),
                ...(envEntries.length > 0 ? { env: envEntries } : {}),

                ...(offer
                    ? {
                          resources: {
                              ...baseResources,
                              ...filterConfiguration.resources,
                              ...getOfferResources(offer),
                          },

                          ...(offer.backend ? { backends: [offer.backend] } : backends?.length ? { backends } : {}),
                          ...(offer.region ? { regions: [offer.region] } : {}),
                          ...(fleets && fleets.length > 0 ? { fleets } : {}),
                          ...(offer.spot.length === 1 ? { spot_policy: offer.spot[0] } : {}),
                          ...(offer.spot.length > 1 ? { spot_policy: 'auto' } : {}),
                      }
                    : {}),
                ...(!offer && hasResourcesParam && !filters && !baseResources
                    ? {
                          resources: {
                              gpu: '1..',
                          },
                      }
                    : {}),

                ...(repo_url || repo_path
                    ? {
                          repos: [[repo_url?.trim(), repo_path?.trim()].filter(Boolean).join(':')],
                      }
                    : {}),

                ...(working_dir ? { working_dir } : {}),
            },
            { lineWidth: -1 },
        );
    }, [formValues, configuration, envParam, hasResourcesParam, backends, fleets, filters]);
};

const getFilterConfiguration = (
    filters: NonNullable<UseFiltersArgs['defaultFilters']>,
    baseResources?: Record<string, unknown>,
) => ({
    resources: {
        ...baseResources,
        gpu:
            filters.gpu_count === '0'
                ? 0
                : [filters.gpu_vendor, filters.gpu_name, filters.gpu_count ?? '1..', filters.gpu_memory]
                      .filter(Boolean)
                      .join(':'),
        cpu: [filters.cpu_arch, filters.cpu_count].filter(Boolean).join(':') || undefined,
        memory: filters.memory,
    },
    backends: filters.backend ? [filters.backend].flat() : undefined,
    fleets: filters.fleet ? [filters.fleet].flat() : undefined,
    regions: filters.region ? [filters.region] : undefined,
    spot_policy: filters.spot_policy,
});
