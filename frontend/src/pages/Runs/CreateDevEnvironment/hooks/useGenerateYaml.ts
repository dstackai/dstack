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

        const { name, ide, image, python, offer, docker, repo_url, repo_path, working_dir, env_type, password } = formValues;

        let baseJson = {
            type: env_type === 'web' ? 'service' : 'dev-environment',
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
        };

        if (env_type === 'web') {
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            const { ide, ...props } = baseJson;

            baseJson = {
                ...props,

                auth: false,
                env: [`PASSWORD=${password}`, 'BIND_ADDR=0.0.0.0:8080'],
                commands: [
                    'curl -fsSL https://code-server.dev/install.sh | sh -s -- --method standalone --prefix /tmp/code-server',
                    '/tmp/code-server/bin/code-server --bind-addr $BIND_ADDR --auth password --disable-telemetry --disable-update-check .',
                ],
                port: 8080,
                gateway: true,
            };
        }

        return jsYaml.dump(baseJson);
    }, [
        formValues.name,
        formValues.env_type,
        formValues.ide,
        formValues.password,
        formValues.offer,
        formValues.python,
        formValues.image,
        formValues.repo_url,
        formValues.repo_path,
        formValues.working_dir,
    ]);
};
