import { useMemo } from 'react';
import jsYaml from 'js-yaml';

import { convertMiBToGB, renderRange, round } from 'pages/Offers/List/helpers';

import { IRunEnvironmentFormValues } from '../types';

export type UseGenerateYamlArgs = {
    formValues: IRunEnvironmentFormValues;
    configuration?: ITemplate['configuration'];
    envParam?: TTemplateParam;
};

export const useGenerateYaml = ({ formValues, configuration, envParam }: UseGenerateYamlArgs) => {
    return useMemo(() => {
        const { name, ide, image, python, offer, docker, repo_url, repo_path, working_dir, password } = formValues;

        const envEntries: string[] = [];
        if (envParam?.name && password) {
            envEntries.push(`${envParam.name}=${password}`);
        }
        if (configuration && 'env' in configuration) {
            envEntries.push(...(configuration['env'] as string[]));
        }

        return jsYaml.dump({
            ...configuration,

            ...(name ? { name } : {}),
            ...(ide ? { ide } : {}),
            ...(docker ? { docker } : {}),
            ...(image ? { image } : {}),
            ...(python ? { python } : {}),
            ...(envEntries.length > 0 ? { env: envEntries } : {}),

            ...(offer
                ? {
                      resources: {
                          gpu: `${offer.name}:${round(convertMiBToGB(offer.memory_mib))}GB:${renderRange(offer.count)}`,
                      },

                      backends: offer.backends,
                      ...(offer.spot.length === 1 ? { spot_policy: offer.spot[0] } : {}),
                      ...(offer.spot.length > 1 ? { spot_policy: 'auto' } : {}),
                  }
                : {}),

            ...(repo_url || repo_path
                ? {
                      repos: [[repo_url?.trim(), repo_path?.trim()].filter(Boolean).join(':')],
                  }
                : {}),

            ...(working_dir ? { working_dir } : {}),
        });
    }, [formValues, configuration, envParam]);
};
