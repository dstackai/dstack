import { useEffect, useMemo } from 'react';

import { SelectCSDProps } from 'components';

import { useGetProjectsQuery } from 'services/project';

import { useLocalStorageState } from './useLocalStorageState';

type Args = {
    localStorePrefix: string;
};

export const useProjectFilter = ({ localStorePrefix }: Args) => {
    const [selectedProject, setSelectedProject] = useLocalStorageState<SelectCSDProps.Option | null>(
        `${localStorePrefix}-project_name`,
        null,
    );

    const { data: projectsData } = useGetProjectsQuery();

    const projectOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!projectsData?.length) return [];

        return projectsData.map((project) => ({ label: project.project_name, value: project.project_name }));
    }, [projectsData]);

    useEffect(() => {
        if (!projectsData || !selectedProject) {
            return;
        }

        const hasSelectedProject = projectsData.some(({ project_name }) => selectedProject?.value === project_name);

        if (!hasSelectedProject) {
            setSelectedProject(null);
        }
    }, [projectsData]);

    return {
        projectOptions,
        selectedProject,
        setSelectedProject,
    } as const;
};
