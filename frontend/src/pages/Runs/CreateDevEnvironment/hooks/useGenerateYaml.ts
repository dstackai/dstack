import { useMemo } from 'react';
import jsYaml from 'js-yaml';

import { convertMiBToGB, renderRange, round } from 'pages/Offers/List/helpers';

import { IRunEnvironmentFormValues } from '../types';

export type UseGenerateYamlArgs = {
    formValues: IRunEnvironmentFormValues;
};

export const useGenerateYaml = ({ formValues }: UseGenerateYamlArgs) => {
    return useMemo(() => {
        if (!formValues.offer || !formValues.ide) {
            return '';
        }

        const { name, ide, image, python, offer, docker, repo_url, repo_path, working_dir } = formValues;

        return jsYaml.dump({
            type: 'dev-environment',
            ...(name ? { name } : {}),
            ide,
            ...(docker ? { docker } : {}),
            ...(image ? { image } : {}),
            ...(python ? { python } : {}),

            resources: {
                gpu: `${offer.name}:${round(convertMiBToGB(offer.memory_mib))}GB:${renderRange(offer.count)}`,
            },

            ...(repo_url || repo_path
                ? {
                      repos: [[repo_url?.trim(), repo_path?.trim()].filter(Boolean).join(':')],
                  }
                : {}),

            ...(working_dir ? { working_dir } : {}),
            backends: offer.backends,
            spot_policy: 'auto',
        });
    }, [
        formValues.name,
        formValues.ide,
        formValues.offer,
        formValues.python,
        formValues.image,
        formValues.repo_url,
        formValues.repo_path,
        formValues.working_dir,
    ]);
};
