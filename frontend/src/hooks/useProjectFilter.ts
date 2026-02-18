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

    const { data: projectsData, isLoading } = useGetProjectsQuery({});

    const projectOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!projectsData?.data?.length) return [];

        return projectsData.data.map((project) => ({ label: project.project_name, value: project.project_name }));
    }, [projectsData]);

    useEffect(() => {
        if (!projectsData?.data || !selectedProject) {
            return;
        }

        const hasSelectedProject = projectsData.data.some(({ project_name }) => selectedProject?.value === project_name);

        if (!hasSelectedProject) {
            setSelectedProject(null);
        }
    }, [projectsData]);

    return {
        projectOptions,
        selectedProject,
        setSelectedProject,
        isLoadingProjectOptions: isLoading,
    } as const;
};
