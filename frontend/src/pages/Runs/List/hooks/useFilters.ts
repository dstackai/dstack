import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { SelectCSDProps } from 'components';

import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { useGetProjectsQuery } from 'services/project';

type Args = {
    localStorePrefix: string;
    projectSearchKey?: string;
    selectedProject?: string;
};

export const useFilters = ({ localStorePrefix, projectSearchKey }: Args) => {
    const [searchParams] = useSearchParams();
    const [selectedProject, setSelectedProject] = useState<SelectCSDProps.Option | null>(null);
    const [onlyActive, setOnlyActive] = useLocalStorageState<boolean>(`${localStorePrefix}-is-active`, false);

    const { data: projectsData } = useGetProjectsQuery();

    const projectOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!projectsData?.length) return [];

        return projectsData.map((project) => ({ label: project.project_name, value: project.project_name }));
    }, [projectsData]);

    const setSelectedOptionFromParams = (
        searchKey: string,
        options: SelectCSDProps.Options | null,
        set: (option: SelectCSDProps.Option) => void,
    ) => {
        const searchValue = searchParams.get(searchKey);

        if (!searchValue || !options?.length) return;

        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        const selectedOption = options.find((option) => option?.value === searchValue);

        if (selectedOption) set(selectedOption);
    };

    useEffect(() => {
        if (!projectSearchKey) return;

        setSelectedOptionFromParams(projectSearchKey, projectOptions, setSelectedProject);
    }, [searchParams, projectSearchKey, projectOptions]);

    const clearSelected = () => {
        setSelectedProject(null);
        setOnlyActive(false);
    };

    const setSelectedProjectHandle = (project: SelectCSDProps.Option | null) => {
        setSelectedProject(project);
        setOnlyActive(false);
    };

    return {
        projectOptions,
        selectedProject,
        setSelectedProject: setSelectedProjectHandle,
        onlyActive,
        setOnlyActive,
        clearSelected,
    } as const;
};
