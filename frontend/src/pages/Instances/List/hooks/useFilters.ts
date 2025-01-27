import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { SelectCSDProps } from 'components';

import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { useGetProjectsQuery } from 'services/project';

export const useFilters = () => {
    const [searchParams, setSearchParams] = useSearchParams();

    const [onlyActive, setOnlyActive] = useLocalStorageState<boolean>('instances-list-is-active', false);
    const [selectedProject, setSelectedProject] = useState<SelectCSDProps.Option | null>(null);

    const { data: projectsData } = useGetProjectsQuery();

    const projectOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!projectsData?.length) return [];

        return projectsData.map((project) => ({ label: project.project_name, value: project.project_name }));
    }, [projectsData]);

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
