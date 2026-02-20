import { useMemo } from 'react';
import jsYaml from 'js-yaml';

import { convertMiBToGB, renderRange, round } from 'pages/Offers/List/helpers';

import { IRunEnvironmentFormValues } from '../types';

export type UseGenerateYamlArgs = {
    formValues: IRunEnvironmentFormValues;
    template?: ITemplate['template'];
};

export const useGenerateYaml = ({ formValues, template }: UseGenerateYamlArgs) => {
    return useMemo(() => {
        const { name, ide, image, python, offer, docker, repo_url, repo_path, working_dir, password } = formValues;

        return jsYaml.dump({
            ...template,

            ...(name ? { name } : {}),
            ...(ide ? { ide } : {}),
            ...(docker ? { docker } : {}),
            ...(image ? { image } : {}),
            ...(python ? { python } : {}),
            ...(template && 'env' in template ? { env: [`PASSWORD=${password}`, ...(template['env'] as string[])] } : {}),

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
    }, [formValues, template]);
};
