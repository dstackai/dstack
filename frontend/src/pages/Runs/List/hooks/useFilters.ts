import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { SelectCSDProps } from 'components';

import { useGetProjectReposQuery, useGetProjectsQuery } from 'services/project';
import { useGetUserListQuery } from 'services/user';

type Args = {
    repoSearchKey?: string;
    projectSearchKey?: string;
    userSearchKey?: string;

    selectedProject?: string;
};
export const useFilters = ({ repoSearchKey, projectSearchKey, userSearchKey, selectedProject: selectedProjectProp }: Args) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [selectedProject, setSelectedProject] = useState<SelectCSDProps.Option | null>(null);
    const [selectedRepo, setSelectedRepo] = useState<SelectCSDProps.Option | null>(null);
    const [selectedUser, setSelectedUser] = useState<SelectCSDProps.Option | null>(null);
    const [onlyActive, setOnlyActive] = useState<boolean>(false);

    useEffect(() => {
        setSelectedRepo(null);
    }, [selectedProjectProp]);

    const { data: projectsData } = useGetProjectsQuery();
    const { data: usersData } = useGetUserListQuery();
    const { data: reposData } = useGetProjectReposQuery(
        {
            project_name: selectedProjectProp ?? selectedProject?.value ?? '',
        },
        {
            skip: !selectedProject && !selectedProjectProp,
        },
    );

    const projectOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!projectsData?.length) return [];

        return projectsData.map((project) => ({ label: project.project_name, value: project.project_name }));
    }, [projectsData]);

    const userOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!usersData?.length) return [];

        return usersData.map((user) => ({ label: user.username, value: user.username }));
    }, [usersData]);

    const repoOptions = useMemo<SelectCSDProps.Options>(() => {
        if (!reposData?.length) return [];

        return reposData.map((repo) => ({ label: repo.repo_id, value: repo.repo_id }));
    }, [reposData]);

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

    useEffect(() => {
        if (!repoSearchKey) return;

        setSelectedOptionFromParams(repoSearchKey, repoOptions, setSelectedRepo);
    }, [searchParams, repoSearchKey, repoOptions]);

    useEffect(() => {
        if (!userSearchKey) return;

        setSelectedOptionFromParams(userSearchKey, userOptions, setSelectedUser);
    }, [searchParams, userSearchKey, userOptions]);

    const clearSelected = () => {
        setSelectedProject(null);
        setSelectedRepo(null);
        setSelectedUser(null);
        setOnlyActive(false);
    };

    const setSelectedProjectHandle = (project: SelectCSDProps.Option | null) => {
        setSelectedProject(project);
        setSelectedRepo(null);
        setOnlyActive(false);
    };

    return {
        projectOptions,
        selectedProject,
        setSelectedProject: setSelectedProjectHandle,
        repoOptions,
        selectedRepo,
        setSelectedRepo,
        userOptions,
        selectedUser,
        setSelectedUser,
        onlyActive,
        setOnlyActive,
        clearSelected,
    } as const;
};
