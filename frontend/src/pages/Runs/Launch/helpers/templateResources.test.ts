import { getTemplateOfferDefaultFilters } from './templateResources';

const makeTemplate = (configuration: Record<string, unknown>): ITemplate =>
    ({
        type: 'template',
        name: 'test',
        title: 'test',
        parameters: [{ type: 'resources' }],
        configuration,
    }) as ITemplate;

describe('templateResources', () => {
    test('includes CPU, RAM and vendor constraints in the resource filters', () => {
        expect(
            getTemplateOfferDefaultFilters(
                makeTemplate({ resources: { gpu: { vendor: 'amd' }, cpu: 'arm:2..8', memory: '1.5GB..4GB' } }),
            ),
        ).toMatchObject({ gpu_vendor: 'amd', cpu_arch: 'arm', cpu_count: '2..8', memory: '1.5GB..4GB' });
    });
    test('returns full gpu name list from object gpu spec', () => {
        const template = makeTemplate({
            type: 'task',
            resources: {
                gpu: {
                    name: ['H100', 'H200'],
                    count: { min: 1, max: 2 },
                },
            },
        });

        expect(getTemplateOfferDefaultFilters(template)).toMatchObject({
            gpu_name: ['H100', 'H200'],
            gpu_count: '1..2',
        });
    });

    test('keeps GB units and open ranges for gpu memory', () => {
        const template = makeTemplate({
            type: 'task',
            resources: {
                gpu: {
                    name: 'H100',
                    memory: { min: '24GB' },
                },
            },
        });

        expect(getTemplateOfferDefaultFilters(template)).toMatchObject({
            gpu_name: 'H100',
            gpu_memory: '24GB..',
        });
    });

    test('adds backends and spot policy defaults', () => {
        const template = makeTemplate({
            type: 'task',
            resources: {
                gpu: 'H100:1',
            },
            backends: ['aws', 'vastai'],
            spot_policy: 'auto',
        });

        expect(getTemplateOfferDefaultFilters(template)).toMatchObject({
            gpu_name: 'H100',
            backend: ['aws', 'vastai'],
            spot_policy: 'auto',
        });
    });

    test('adds fleet defaults', () => {
        const template = makeTemplate({
            type: 'task',
            resources: {
                gpu: 'H100:1',
            },
            fleets: ['team-a', 'other-project/team-b'],
        });

        expect(getTemplateOfferDefaultFilters(template)).toMatchObject({
            gpu_name: 'H100',
            fleet: ['team-a', 'other-project/team-b'],
        });
    });
});
