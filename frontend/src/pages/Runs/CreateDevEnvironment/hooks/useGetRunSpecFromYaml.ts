import { useCallback } from 'react';
import jsYaml from 'js-yaml';

import { useNotifications } from 'hooks';
import { useInitRepoMutation, useLazyGetRepoQuery } from 'services/repo';

import { getPathWithoutProtocol, getRepoDirFromUrl, getRepoName, getRepoUrlWithOutDir, slugify } from '../../../../libs/repo';
import { getRunSpecConfigurationResources } from '../helpers/getRunSpecConfigurationResources';

// TODO add next fields: volumes, repos,
const supportedFields: (keyof TDevEnvironmentConfiguration)[] = [
    'type',
    'init',
    'inactivity_duration',
    'image',
    'user',
    'privileged',
    'entrypoint',
    'working_dir',
    'registry_auth',
    'python',
    'nvcc',
    'env',
    'docker',
    'backends',
    'regions',
    'instance_types',
    'spot_policy',
    'retry',
    'max_duration',
    'max_price',
    'idle_duration',
    'utilization_policy',
    'fleets',
    'repos',
];

export const useGetRunSpecFromYaml = ({ projectName = '' }) => {
    const [pushNotification] = useNotifications();
    const [getRepo] = useLazyGetRepoQuery();
    const [initRepo] = useInitRepoMutation();

    const getRepoData = useCallback(
        async (repos: string[]) => {
            const [firstRepo] = repos;

            if (!firstRepo) {
                return {};
            }

            const repoUrlWithoutDir = getRepoUrlWithOutDir(firstRepo);
            const prefix = getRepoName(repoUrlWithoutDir);
            const uniqKey = getPathWithoutProtocol(repoUrlWithoutDir);
            const repoId = await slugify(prefix, uniqKey);
            const repoDir = getRepoDirFromUrl(firstRepo);

            try {
                await getRepo({ project_name: projectName, repo_id: repoId, include_creds: true }).unwrap();
            } catch (_) {
                await initRepo({
                    project_name: projectName,
                    repo_id: repoId,
                    repo_info: {
                        repo_type: 'remote',
                        repo_name: prefix,
                    },
                    repo_creds: { clone_url: repoUrlWithoutDir, private_key: null, oauth_token: null },
                })
                    .unwrap()
                    .catch(console.error);
            }

            return {
                repo_id: repoId,
                repo_data: {
                    repo_type: 'remote',
                    repo_name: prefix,
                    repo_branch: null,
                    repo_hash: null,
                    repo_config_name: null,
                    repo_config_email: null,
                },
                repo_code_hash: null,
                repo_dir: repoDir ?? null,
            };
        },
        [projectName, getRepo, initRepo],
    );

    const getRunSpecFromYaml = useCallback(
        async (yaml: string) => {
            let parsedYaml;

            try {
                parsedYaml = (await jsYaml.load(yaml)) as { [key: string]: unknown };
                // eslint-disable-next-line @typescript-eslint/no-unused-vars
            } catch (_) {
                pushNotification({
                    type: 'error',
                    content: 'Invalid YAML',
                });

                window.scrollTo(0, 0);

                throw new Error('Invalid YAML');
            }

            const { name, ...otherFields } = parsedYaml;

            const runSpec: TRunSpec = {
                run_name: name as string,
                configuration: {} as TDevEnvironmentConfiguration,
            };

            for (const fieldName of Object.keys(otherFields)) {
                switch (fieldName) {
                    case 'ide':
                        runSpec.configuration.ide = otherFields[fieldName] as TIde;
                        break;
                    case 'resources':
                        runSpec.configuration.resources = getRunSpecConfigurationResources(otherFields[fieldName]);
                        break;
                    case 'repos': {
                        const repoData = await getRepoData(otherFields['repos'] as TEnvironmentConfigurationRepo[]);
                        Object.assign(runSpec, repoData);
                        break;
                    }
                    default:
                        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                        // @ts-expect-error
                        if (!supportedFields.includes(fieldName)) {
                            throw new Error(`Unsupported field: ${fieldName}`);
                        }
                        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                        // @ts-expect-error
                        runSpec.configuration[fieldName] = otherFields[fieldName];
                        break;
                }
            }

            return runSpec;
        },
        [pushNotification, getRepoData],
    );

    return [getRunSpecFromYaml];
};
