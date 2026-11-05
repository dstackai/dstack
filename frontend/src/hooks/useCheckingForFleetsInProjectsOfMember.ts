import { useMemo } from 'react';

import { useGetOnlyNoFleetsProjectsQuery } from 'services/project';

type Args = { projectNames: IProject['project_name'][] };

export const useCheckingForFleetsInProjects = ({ projectNames }: Args) => {
    const { data: noFleetsProjectsData } = useGetOnlyNoFleetsProjectsQuery();

    const projectHavingFleetMap = useMemo<Record<IProject['project_name'], boolean>>(() => {
        const map: Record<IProject['project_name'], boolean> = {};

        projectNames.forEach((projectName) => {
            map[projectName] = !noFleetsProjectsData?.some((i) => i.project_name === projectName);
        });

        return map;
    }, [projectNames, noFleetsProjectsData]);

    return projectHavingFleetMap;
};

export const useNewestProjectWithoutFleets = (): IProject['project_name'] | undefined => {
    const { data: noFleetsProjectsData } = useGetOnlyNoFleetsProjectsQuery();

    // The endpoint sorts projects by ascending creation time
    return noFleetsProjectsData?.[noFleetsProjectsData.length - 1]?.project_name;
};
