import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

import { SelectCSDProps } from 'components';

import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { useProjectFilter } from 'hooks/useProjectFilter';

type Args = {
    localStorePrefix: string;
    projectSearchKey?: string;
    selectedProject?: string;
};

export const useFilters = ({ localStorePrefix, projectSearchKey }: Args) => {
    const [searchParams] = useSearchParams();
    const { selectedProject, setSelectedProject, projectOptions } = useProjectFilter({ localStorePrefix });
    const [onlyActive, setOnlyActive] = useLocalStorageState<boolean>(`${localStorePrefix}-is-active`, false);

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
