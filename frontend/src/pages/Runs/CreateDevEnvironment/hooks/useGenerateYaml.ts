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

        const { name, ide, docker, image, python, offer, repo, repo_local_path } = formValues;

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

            ...(repo || repo_local_path
                ? {
                      repos: [
                          {
                              ...(repo ? { url: repo } : {}),
                              ...(repo_local_path ? { local_path: repo_local_path } : {}),
                          },
                      ],
                  }
                : {}),

            backends: offer.backends,
            spot_policy: 'auto',
        });
    }, [
        formValues.name,
        formValues.ide,
        formValues.offer,
        formValues.python,
        formValues.image,
        formValues.repo,
        formValues.repo_local_path,
    ]);
};
