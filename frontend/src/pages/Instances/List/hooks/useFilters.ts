import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { useProjectFilter } from 'hooks/useProjectFilter';

export const useFilters = (localStorePrefix = 'instances-list-page') => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [onlyActive, setOnlyActive] = useLocalStorageState<boolean>(`${localStorePrefix}-is-active`, false);
    const { selectedProject, setSelectedProject, projectOptions } = useProjectFilter({ localStorePrefix });

    const clearFilters = () => {
        setOnlyActive(false);
        setSelectedProject(null);

        setSearchParams((prev) => {
            prev.delete('fleetId');
            return prev;
        });
    };

    const selectedFleet = useMemo(() => {
        const fleetName = searchParams.get('fleetId');

        if (fleetName) {
            return { label: fleetName, value: fleetName };
        }

        return null;
    }, [searchParams]);

    const isDisabledClearFilter = !selectedProject && !onlyActive && !selectedFleet;

    return {
        projectOptions,
        selectedProject,
        setSelectedProject,
        selectedFleet,
        onlyActive,
        setOnlyActive,
        clearFilters,
        isDisabledClearFilter,
    } as const;
};
