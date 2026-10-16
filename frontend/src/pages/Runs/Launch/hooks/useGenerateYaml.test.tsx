import React from 'react';
import { act, create, ReactTestRenderer } from 'react-test-renderer';
import jsYaml from 'js-yaml';

import { tokensToSearchParams } from 'libs/filters';

import { getOfferResources, OfferCard, toCpuCard } from 'pages/Offers/List/helpers';
import { toRangeTokens } from 'pages/Offers/List/hooks/useFilters';

import { getRunSpecConfigurationResources } from '../helpers/getRunSpecConfigurationResources';
import { useGenerateYaml, UseGenerateYamlArgs } from './useGenerateYaml';

const generate = (args: Partial<UseGenerateYamlArgs>) => {
    let yaml = '';
    const Harness = () => {
        yaml = useGenerateYaml({ formValues: {} as UseGenerateYamlArgs['formValues'], ...args });
        return null;
    };
    let renderer: ReactTestRenderer;
    act(() => {
        renderer = create(<Harness />);
    });
    act(() => renderer.unmount());
    return jsYaml.load(yaml);
};

describe('useGenerateYaml', () => {
    const configuration = { type: 'task', resources: { gpu: 'H100:1', disk: '100GB' } } as ITemplate['configuration'];
    const offer: OfferCard = {
        name: 'H100',
        vendor: 'nvidia',
        memory_mib: 275032,
        count: { min: 1, max: 2 },
        price: { min: 1, max: 2 },
        availability: ['available'],
        spot: ['on-demand'],
        backend: 'aws',
        region: 'eu-west-1',
    };

    test('CPU selection overrides template GPU and preserves unrelated resources', () => {
        const cpu: OfferCard = {
            ...offer,
            count: { min: 2, max: 2 },
            memory_mib: 1901,
            cpu: { cpus: 2, cpu_arch: 'arm', memory_mib: 1901, gpus: [], spot: false },
        };
        expect(
            generate({ configuration, formValues: { offer: cpu } as UseGenerateYamlArgs['formValues'], fleets: ['chosen'] }),
        ).toEqual({
            type: 'task',
            resources: { gpu: 0, cpu: 'arm:2', memory: '1.8564453125GB', disk: '100GB' },
            backends: ['aws'],
            regions: ['eu-west-1'],
            fleets: ['chosen'],
            spot_policy: 'on-demand',
        });
    });

    test('GPU selection keeps exact VRAM and count range without inferring a fleet', () => {
        expect(generate({ configuration, formValues: { offer } as UseGenerateYamlArgs['formValues'] })).toEqual({
            type: 'task',
            resources: { gpu: 'nvidia:H100:1..2:268.5859375GB', disk: '100GB' },
            backends: ['aws'],
            regions: ['eu-west-1'],
            spot_policy: 'on-demand',
        });
    });

    test('no selection keeps explicit template resources, otherwise defaults to GPU', () => {
        expect(generate({ configuration, hasResourcesParam: true })).toEqual(configuration);
        const cpuConfiguration = { type: 'task', resources: { cpu: 2, memory: '4GB' } } as ITemplate['configuration'];
        expect(generate({ configuration: cpuConfiguration, hasResourcesParam: true })).toEqual(cpuConfiguration);
        expect(generate({ configuration: { type: 'task' } as ITemplate['configuration'], hasResourcesParam: true })).toEqual({
            type: 'task',
            resources: { gpu: '1..' },
        });
    });

    test('CPU filters apply without a card selection and keep unrelated template resources', () => {
        expect(
            generate({
                configuration,
                hasResourcesParam: true,
                filters: { gpu_count: '0', cpu_count: '2..32', cpu_arch: 'arm', memory: '1.5GB..', fleet: ['chosen'] },
            }),
        ).toEqual({
            type: 'task',
            resources: { gpu: 0, cpu: 'arm:2..32', memory: '1.5GB..', disk: '100GB' },
            fleets: ['chosen'],
        });
    });

    test('cleared filters remove template constraints and re-enable GPUs', () => {
        expect(
            generate({
                configuration: { ...configuration, backends: ['aws'], resources: { gpu: 0, cpu: 8, memory: '16GB' } },
                hasResourcesParam: true,
                filters: {},
            }),
        ).toEqual({ type: 'task', resources: { gpu: '1..' } });
    });

    test('CPU ranges and fractional memory survive RunSpec conversion', () => {
        const cpu = toCpuCard({
            cpu_arch: ['arm', 'x86'],
            count: { min: 2, max: 32 },
            memory_mib: { min: 1901, max: 65536 },
            price: { min: 0, max: 1 },
            availability: ['idle'],
            spot: ['on-demand'],
        });
        expect(getRunSpecConfigurationResources(getOfferResources(cpu))).toEqual({
            gpu: 0,
            cpu: '2..32',
            memory: { min: 1.8564453125, max: 64 },
        });
        expect(getRunSpecConfigurationResources({ memory: '..4.5GB' })).toEqual({ memory: { max: 4.5 } });
    });

    test('GPU count and fractional VRAM survive RunSpec conversion', () => {
        expect(getRunSpecConfigurationResources(getOfferResources(offer))).toEqual({
            gpu: {
                vendor: 'nvidia',
                name: ['H100'],
                count: { min: 1, max: 2 },
                memory: { min: 268.5859375, max: 268.5859375 },
            },
        });
        expect(getRunSpecConfigurationResources({ gpu: 'H100:1' })).toMatchObject({
            gpu: { count: { min: 1, max: 1 } },
        });
    });

    test('Launch URL serialization preserves comparison operators', () => {
        const params = tokensToSearchParams(
            toRangeTokens([
                { propertyKey: 'memory', operator: '>=', value: '4GB' },
                { propertyKey: 'gpu_count', operator: '<=', value: '8' },
            ]),
        );
        expect(params.get('memory')).toBe('4GB..');
        expect(params.get('gpu_count')).toBe('..8');
    });
});
