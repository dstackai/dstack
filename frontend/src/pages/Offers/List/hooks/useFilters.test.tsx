/** @jest-environment node */
import React from 'react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { act, create, ReactTestRenderer } from 'react-test-renderer';

import { getOfferFilters, useFilters, UseFiltersArgs } from './useFilters';

let mockRememberedProject: string | null;
const mockSetRememberedProject = jest.fn();
let mockProjectsData: { data: { project_name: string }[] } | undefined;
const mockGetProject = jest.fn();

jest.mock('hooks/useLocalStorageState', () => ({
    useLocalStorageState: () => [mockRememberedProject, mockSetRememberedProject],
}));
jest.mock('services/fleet', () => ({ useLazyGetProjectFleetsQuery: () => [jest.fn()] }));
jest.mock('services/project', () => ({
    useLazyGetProjectsQuery: () => [jest.fn()],
    useGetProjectsQuery: () => ({ data: mockProjectsData }),
    useLazyGetProjectQuery: () => [mockGetProject],
}));
let filters: ReturnType<typeof useFilters>;
let search: string;
let renderer: ReactTestRenderer;

const Harness = (props: Partial<UseFiltersArgs>) => {
    filters = useFilters({ gpus: [], ...props });
    search = useLocation().search;
    return null;
};

const renderFilters = (url: string, props: Partial<UseFiltersArgs> = {}) => {
    act(() => {
        renderer = create(
            <MemoryRouter initialEntries={[url]}>
                <Harness {...props} />
            </MemoryRouter>,
        );
    });
};

beforeEach(() => {
    mockRememberedProject = null;
    mockProjectsData = undefined;
    mockGetProject.mockReset();
});

afterEach(() => act(() => renderer.unmount()));

describe('Offer filters', () => {
    test('remembers the selected project', () => {
        renderFilters('/?project_name=main');
        expect(mockSetRememberedProject).toHaveBeenCalledWith('main');
    });

    test('restores a valid remembered project even outside the first page of projects', async () => {
        mockRememberedProject = 'saved';
        mockProjectsData = { data: [{ project_name: 'first' }, { project_name: 'second' }] };
        mockGetProject.mockReturnValue({ unwrap: () => Promise.resolve({ project_name: 'saved' }) });
        renderFilters('/');
        await act(async () => {});
        expect(mockGetProject).toHaveBeenCalledWith({ name: 'saved' }, false);
        expect(filters.filteringRequestParams.project_name).toBe('saved');
        expect(new URLSearchParams(search).get('project_name')).toBe('saved');
    });

    test('waits for the remembered project to be revalidated before restoring it', () => {
        mockRememberedProject = 'saved';
        mockProjectsData = { data: [{ project_name: 'other' }] };
        mockGetProject.mockReturnValue({ unwrap: () => new Promise(() => {}) });
        renderFilters('/');
        expect(filters.filteringRequestParams.project_name).toBeUndefined();
    });

    test('does not overwrite a project selected while the remembered project is being checked', async () => {
        mockRememberedProject = 'saved';
        mockProjectsData = { data: [{ project_name: 'first' }, { project_name: 'second' }] };
        let resolveProject!: (project: { project_name: string }) => void;
        mockGetProject.mockReturnValue({
            unwrap: () =>
                new Promise((resolve) => {
                    resolveProject = resolve;
                }),
        });
        renderFilters('/');
        act(() =>
            filters.onChangePropertyFilter!({
                detail: { operation: 'and', tokens: [{ propertyKey: 'project_name', operator: '=', value: 'chosen' }] },
            } as never),
        );
        await act(async () => {
            resolveProject({ project_name: 'saved' });
        });
        expect(filters.filteringRequestParams.project_name).toBe('chosen');
    });

    test.each([403, 404])('discards a remembered project returning %s and keeps the project prompt', async (status) => {
        mockRememberedProject = 'removed';
        mockProjectsData = { data: [{ project_name: 'first' }, { project_name: 'second' }] };
        mockGetProject.mockReturnValue({ unwrap: () => Promise.reject({ status }) });
        renderFilters('/');
        await act(async () => {});
        expect(filters.filteringRequestParams.project_name).toBeUndefined();
        expect(mockSetRememberedProject).toHaveBeenCalledWith(null);
    });

    test('an explicit project takes priority over the remembered project', () => {
        mockRememberedProject = 'saved';
        renderFilters('/?project_name=main');
        expect(filters.filteringRequestParams.project_name).toBe('main');
        expect(mockGetProject).not.toHaveBeenCalled();
    });

    test('a fleet project does not replace the remembered selection', () => {
        mockRememberedProject = 'saved';
        renderFilters('/', { permanentFilters: { project_name: 'fixed', fleet: 'my-fleet' } });
        expect(filters.filteringRequestParams.project_name).toBe('fixed');
        expect(mockSetRememberedProject).not.toHaveBeenCalled();
        expect(mockGetProject).not.toHaveBeenCalled();
    });

    test('GPU toggle selects CPUs, clears GPU constraints, and restores grouping', () => {
        renderFilters(
            '/?project_name=main&gpu_vendor=nvidia&gpu_name=H100&gpu_count=8&memory=4GB&group_by=gpu&group_by=backend',
            {
                allowUngrouped: true,
            },
        );
        expect(filters.gpuEnabled).toBe(true);
        expect(filters.canAutoSelectCpu).toBe(false);

        act(() => filters.onChangeGpu(false));
        expect(filters.gpuEnabled).toBe(false);
        expect(filters.canAutoSelectCpu).toBe(false);
        expect(filters.filteringRequestParams).toEqual({ project_name: 'main', gpu_count: '0', memory: '4GB' });
        expect(filters.propertyFilterQuery.tokens).toContainEqual({ propertyKey: 'gpu_count', operator: '=', value: '0' });
        expect(filters.filteringProperties.filter(({ key }) => key.startsWith('gpu_')).map(({ key }) => key)).toEqual([
            'gpu_count',
        ]);
        expect(new URLSearchParams(search).get('gpu_count')).toBe('0');
        expect(new URLSearchParams(search).getAll('group_by')).toEqual(['cpu', 'backend']);
        expect(filters.groupBy.map(({ value }) => value)).toEqual(['cpu', 'backend']);

        act(() => filters.onChangeGpu(true));
        expect(filters.gpuEnabled).toBe(true);
        expect(filters.filteringRequestParams).toEqual({ project_name: 'main', memory: '4GB' });
        expect(filters.groupBy.map(({ value }) => value)).toEqual(['gpu', 'backend']);
    });

    test('CPU mode survives filter edits and clearing, and a CPU deep link can enable GPU grouping', () => {
        renderFilters('/?project_name=main&gpu_count=0', { allowUngrouped: true });
        expect(filters.gpuEnabled).toBe(false);
        expect(filters.hasCustomFilters).toBe(false);
        act(() =>
            filters.onChangePropertyFilter!({
                detail: {
                    operation: 'and',
                    tokens: [
                        { propertyKey: 'project_name', operator: '=', value: 'main' },
                        { propertyKey: 'gpu_count', operator: '=', value: '0' },
                        { propertyKey: 'memory', operator: '>=', value: '4GB' },
                    ],
                },
            } as never),
        );
        expect(filters.filteringRequestParams).toMatchObject({ gpu_count: '0', memory: '4GB..' });
        act(() => filters.clearFilter());
        expect(filters.filteringRequestParams).toEqual({ project_name: 'main', gpu_count: '0' });
        expect(filters.hasCustomFilters).toBe(false);
        act(() => filters.onChangeGpu(true));
        expect(filters.gpuEnabled).toBe(true);
        expect(filters.groupBy.map(({ value }) => value)).toEqual(['gpu']);
    });

    test('resource bounds keep their units and range semantics in requests and URLs', () => {
        renderFilters('/', { allowUngrouped: true });
        act(() =>
            filters.onChangePropertyFilter!({
                detail: {
                    operation: 'and',
                    tokens: [
                        { propertyKey: 'memory', operator: '>=', value: '4GB' },
                        { propertyKey: 'gpu_count', operator: '<=', value: '8' },
                    ],
                },
            } as never),
        );
        expect(filters.filteringRequestParams).toMatchObject({ memory: '4GB..', gpu_count: '..8' });
        expect(new URLSearchParams(search).get('memory')).toBe('4GB..');
        expect(new URLSearchParams(search).get('gpu_count')).toBe('..8');
    });

    test('reports edits, and restores wizard filters and grouping without changing the URL', () => {
        const onChange = jest.fn();
        renderFilters('/?template=test', { withSearchParams: false, allowUngrouped: true, onChange });
        expect(onChange).not.toHaveBeenCalled();
        act(() => filters.onChangeGroupBy!({ detail: { selectedOptions: [] } } as never));
        expect(onChange).toHaveBeenLastCalledWith({ group_by: [] });
        expect(search).toBe('?template=test');

        act(() => renderer.unmount());
        renderFilters('/?template=test', {
            withSearchParams: false,
            allowUngrouped: true,
            defaultFilters: { gpu_count: '0', cpu_count: '2', group_by: [] },
        });
        expect(filters.groupBy).toEqual([]);
        expect(filters.filteringRequestParams).toEqual({ gpu_count: '0', cpu_count: '2' });
        expect(filters.propertyFilterQuery.tokens.map(({ propertyKey }) => propertyKey)).not.toContain('group_by');
    });

    test('a CPU selection can open individual offers and survives Launch filters', () => {
        renderFilters('/?gpu_count=0&cpu_count=2&cpu_arch=arm&memory=1.8564453125GB&region=cluster&group_by=', {
            allowUngrouped: true,
        });
        expect(filters.groupBy).toEqual([]);
        expect(
            getOfferFilters(new URLSearchParams('?gpu_count=0&cpu_count=2&cpu_arch=arm&memory=1.8564453125GB&region=cluster')),
        ).toEqual({
            gpu_count: '0',
            cpu_count: '2',
            cpu_arch: 'arm',
            memory: '1.8564453125GB',
            region: 'cluster',
        });
    });

    test('GPU vendor suggestions come from offers and preserve API values in URLs and launch filters', async () => {
        const gpu: IGpu = {
            name: 'H100',
            vendor: 'nvidia',
            memory_mib: 81920,
            count: { min: 1, max: 8 },
            price: { min: 1, max: 8 },
            availability: ['available'],
            spot: ['on-demand'],
        };
        const loadGpus = jest.fn();
        renderFilters('/?project_name=main&gpu_vendor=amd', {
            gpus: [gpu, { ...gpu, name: 'A100' }, { ...gpu, name: 'v5p', vendor: 'google' }],
            loadGpus,
        });
        expect(filters.filteringRequestParams.gpu_vendor).toBe('amd');
        expect(filters.filteringProperties.find(({ key }) => key === 'gpu_vendor')?.propertyLabel).toBe('GPU vendor');
        expect(
            filters.filteringOptions.filter(({ propertyKey }) => propertyKey === 'gpu_vendor').map(({ value }) => value),
        ).toEqual(['nvidia', 'google']);
        expect(filters.filteringOptions.find(({ value }) => value === 'google')?.label).toBe('TPU');

        await act(async () => {
            await filters.handleLoadItems!({
                detail: { filteringProperty: { key: 'gpu_vendor' }, filteringText: '' },
            } as never);
        });
        expect(loadGpus).toHaveBeenCalledWith('main');

        act(() =>
            filters.onChangePropertyFilter!({
                detail: {
                    operation: 'and',
                    tokens: [
                        { propertyKey: 'project_name', operator: '=', value: 'main' },
                        { propertyKey: 'gpu_vendor', operator: '=', value: 'nvidia' },
                    ],
                },
            } as never),
        );
        expect(new URLSearchParams(search).get('gpu_vendor')).toBe('nvidia');
        expect(getOfferFilters(new URLSearchParams(search))?.gpu_vendor).toBe('nvidia');
    });

    test('defaults to GPU grouping and preserves explicitly ungrouped URLs', () => {
        renderFilters('/', { allowUngrouped: true });
        expect(filters.gpuEnabled).toBe(true);
        expect(filters.canAutoSelectCpu).toBe(true);
        expect(filters.groupBy.map(({ value }) => value)).toEqual(['gpu']);

        act(() => filters.onChangeGroupBy!({ detail: { selectedOptions: [] } } as never));
        expect(filters.groupBy).toEqual([]);
        expect(new URLSearchParams(search).has('group_by')).toBe(true);
        expect(new URLSearchParams(search).get('group_by')).toBe('');

        act(() => renderer.unmount());
        renderFilters(`/${search}`, { allowUngrouped: true });
        expect(filters.groupBy).toEqual([]);
    });

    test.each(['gpu_count=0', 'gpu_count=0&group_by=gpu', 'group_by=cpu'])('%s selects CPU grouping', (query) => {
        renderFilters(`/?project_name=main&${query}`, { allowUngrouped: true });
        expect(filters.gpuEnabled).toBe(false);
        expect(filters.filteringRequestParams.gpu_count).toBe('0');
        expect(filters.groupBy).toEqual([{ label: 'CPU', value: 'cpu' }]);
        expect(filters.groupByOptions.map(({ label }) => label)).toEqual(['CPU', 'Backend']);
    });

    test.each(['..0', '0..0'])('zero GPU range %s selects CPU grouping', (value) => {
        renderFilters(`/?project_name=main&gpu_count=${value}`, { allowUngrouped: true });
        expect(filters.gpuEnabled).toBe(false);
        expect(filters.groupBy).toEqual([{ label: 'CPU', value: 'cpu' }]);
    });

    test('an upper bound of zero selects CPU grouping', () => {
        renderFilters('/?project_name=main', { allowUngrouped: true });
        act(() =>
            filters.onChangePropertyFilter!({
                detail: { operation: 'and', tokens: [{ propertyKey: 'gpu_count', operator: '<=', value: '0' }] },
            } as never),
        );
        expect(filters.gpuEnabled).toBe(false);
        expect(filters.groupBy).toEqual([{ label: 'CPU', value: 'cpu' }]);
        expect(new URLSearchParams(search).get('gpu_count')).toBe('..0');
    });

    test('removing the visible zero GPU count enables GPU and updates grouping', () => {
        renderFilters('/?project_name=main&gpu_count=0&group_by=cpu', { allowUngrouped: true });
        act(() =>
            filters.onChangePropertyFilter!({
                detail: { operation: 'and', tokens: [{ propertyKey: 'project_name', operator: '=', value: 'main' }] },
            } as never),
        );
        expect(filters.gpuEnabled).toBe(true);
        expect(filters.groupBy).toEqual([{ label: 'GPU', value: 'gpu' }]);
        expect(new URLSearchParams(search).has('gpu_count')).toBe(false);
        expect(new URLSearchParams(search).get('group_by')).toBe('gpu');
    });

    test('Clear filter keeps the project and CPU mode', () => {
        renderFilters('/?project_name=main&gpu_count=0&memory=4GB&group_by=cpu', { allowUngrouped: true });
        act(() => filters.clearFilter());
        expect(filters.filteringRequestParams).toEqual({ project_name: 'main', gpu_count: '0' });
        expect(filters.groupBy).toEqual([{ label: 'CPU', value: 'cpu' }]);
        expect(new URLSearchParams(search).get('project_name')).toBe('main');
    });

    test('removing the only CPU mode token enables GPU in a fleet', () => {
        renderFilters('/?gpu_count=0&group_by=cpu', {
            allowUngrouped: true,
            permanentFilters: { project_name: 'main', fleet: 'cpu-fleet' },
        });
        act(() => filters.onChangePropertyFilter!({ detail: { operation: 'and', tokens: [] } } as never));
        expect(filters.gpuEnabled).toBe(true);
        expect(filters.groupBy).toEqual([{ label: 'GPU', value: 'gpu' }]);
    });

    test('fixed fleet scope overrides URL filters and is serialized as an array', () => {
        renderFilters('/?project_name=other&fleet=other&backend=aws', {
            permanentFilters: { project_name: 'main', fleet: 'my-fleet' },
            allowUngrouped: true,
        });
        expect(filters.filteringRequestParams).toMatchObject({
            project_name: 'main',
            fleet: ['my-fleet'],
            backend: ['aws'],
        });
        expect(filters.propertyFilterQuery.tokens.map(({ propertyKey }) => propertyKey)).toEqual(['backend']);
        expect(filters.filteringProperties.map(({ key }) => key)).not.toContain('project_name');
        expect(filters.filteringProperties.map(({ key }) => key)).not.toContain('fleet');

        act(() => filters.clearFilter());
        expect(filters.filteringRequestParams).toEqual({ project_name: 'main', fleet: ['my-fleet'] });
        expect(filters.hasCustomFilters).toBe(false);
    });

    test('global fleet deep links keep their filter until the project changes', () => {
        renderFilters('/?project_name=main&fleet=my-fleet', { showFleetFilter: true });
        expect(filters.filteringRequestParams.fleet).toEqual(['my-fleet']);

        act(() =>
            filters.onChangePropertyFilter!({
                detail: {
                    operation: 'and',
                    tokens: [
                        { propertyKey: 'project_name', operator: '=', value: 'other' },
                        { propertyKey: 'fleet', operator: '=', value: 'my-fleet' },
                    ],
                },
            } as never),
        );
        expect(filters.filteringRequestParams.project_name).toBe('other');
        expect(filters.filteringRequestParams.fleet).toBeUndefined();
    });
});
