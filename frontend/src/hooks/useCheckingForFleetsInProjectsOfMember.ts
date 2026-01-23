import { useMemo } from 'react';

import { useGetOnlyNoFleetsProjectsQuery, useGetProjectsQuery } from 'services/project';

type Args = { projectNames?: IProject['project_name'][] };

export const useCheckingForFleetsInProjects = ({ projectNames }: Args) => {
    const { data: projectsData } = useGetProjectsQuery(undefined, {
        skip: !!projectNames?.length,
    });

    const { data: noFleetsProjectsData } = useGetOnlyNoFleetsProjectsQuery();

    const projectNameForChecking = useMemo<IProject['project_name'][]>(() => {
        if (projectNames) {
            return projectNames;
        }

        if (projectsData) {
            return projectsData.map((project) => project.project_name);
        }

        return [];
    }, [projectNames, projectsData]);

    const projectHavingFleetMap = useMemo<Record<IProject['project_name'], boolean>>(() => {
        const map: Record<IProject['project_name'], boolean> = {};

        projectNameForChecking.forEach((projectName) => {
            map[projectName] = !noFleetsProjectsData?.some((i) => i.project_name === projectName);
        });

        return map;
    }, [projectNameForChecking, noFleetsProjectsData]);

    return projectHavingFleetMap;
};
