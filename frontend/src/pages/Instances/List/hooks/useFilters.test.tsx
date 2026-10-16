/** @jest-environment node */
import React from 'react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { act, create, ReactTestRenderer } from 'react-test-renderer';

import { useFilters } from './useFilters';

jest.mock('hooks', () => ({
    useLocalStorageState: (_key: string, value: boolean) => jest.requireActual('react').useState(value),
}));
jest.mock('services/project', () => ({ useLazyGetProjectsQuery: () => [jest.fn()] }));

let filters: ReturnType<typeof useFilters>;
let search: string;
let renderer: ReactTestRenderer;

const Harness = ({ fleetId }: { fleetId?: string }) => {
    filters = useFilters(fleetId);
    search = useLocation().search;
    return null;
};

const renderFilters = (url: string, fleetId?: string) => {
    act(() => {
        renderer = create(
            <MemoryRouter initialEntries={[url]}>
                <Harness fleetId={fleetId} />
            </MemoryRouter>,
        );
    });
};

afterEach(() => act(() => renderer.unmount()));

test('embedded instances stay scoped to the fleet without changing the fleet page URL', () => {
    const query = '?project_names=other&fleet_ids=other&gpu_count=0';
    renderFilters(`/${query}`, 'fixed-fleet');
    expect(filters.filteringRequestParams).toEqual({
        fleet_ids: ['fixed-fleet'],
        only_active: true,
        include_imported: true,
    });

    act(() => filters.onChangeOnlyActive!({ detail: { checked: false } } as never));
    act(() => filters.clearFilter());
    expect(filters.filteringRequestParams).toEqual({
        fleet_ids: ['fixed-fleet'],
        only_active: false,
        include_imported: true,
    });
    expect(search).toBe(query);
});

test('global instances still read and clear URL filters', () => {
    renderFilters('/?project_names=main&fleet_ids=my-fleet');
    expect(filters.filteringRequestParams).toMatchObject({ project_names: ['main'], fleet_ids: ['my-fleet'] });
    act(() => filters.clearFilter());
    expect(filters.filteringRequestParams).toEqual({ only_active: true, include_imported: true });
    expect(search).toBe('');
});
