import jsYaml from 'js-yaml';

import { getRunSpecConfigurationResources } from './getRunSpecConfigurationResources';

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
];

export const getRunSpecFromYaml = async (yaml: string) => {
    let parsedYaml;

    try {
        parsedYaml = (await jsYaml.load(yaml)) as { [key: string]: unknown };
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
    } catch (_) {
        throw new Error(`Invalid YAML`);
    }

    const { name, ...otherFields } = parsedYaml;

    const runSpec: Omit<TRunSpec, 'ssh_key_pub'> = {
        run_name: name as string,
        configuration: {} as TDevEnvironmentConfiguration,
    };

    Object.keys(otherFields).forEach((fieldName) => {
        switch (fieldName) {
            case 'ide':
                runSpec.configuration.ide = otherFields[fieldName] as TIde;
                break;
            case 'resources':
                runSpec.configuration.resources = getRunSpecConfigurationResources(otherFields[fieldName]);
                break;
            default:
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                if (!supportedFields.includes(fieldName)) {
                    throw new Error(`Unsupported field: ${fieldName}`);
                }
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                runSpec.configuration[fieldName] = otherFields[fieldName];
                return {};
        }
    });

    return runSpec;
};
