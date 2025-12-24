import { useEffect, useMemo, useState } from 'react';

import { useLazyGetFleetsQuery } from '../services/fleet';
import { useGetProjectsQuery } from '../services/project';

type Args = { projectNames?: IProject['project_name'][] };

export const useCheckingForFleetsInProjects = ({ projectNames }: Args) => {
    const [projectFleetMap, setProjectFleetMap] = useState<Record<IProject['project_name'], boolean>>({});
    const { data: projectsData } = useGetProjectsQuery(undefined, {
        skip: !!projectNames?.length,
    });

    const [getFleets] = useLazyGetFleetsQuery();

    const projectNameForChecking = useMemo<IProject['project_name'][]>(() => {
        if (projectNames) {
            return projectNames;
        }

        if (projectsData) {
            return projectsData.map((project) => project.project_name);
        }

        return [];
    }, [projectNames, projectsData]);

    useEffect(() => {
        const fetchFleets = async () => {
            const map: Record<IProject['project_name'], boolean> = {};

            await Promise.all(
                projectNameForChecking.map((projectName) =>
                    getFleets({
                        limit: 1,
                        project_name: projectName,
                    })
                        .unwrap()
                        .then((data) => (map[projectName] = Boolean(data.length))),
                ),
            );

            setProjectFleetMap(map);
        };

        fetchFleets();
    }, [projectNameForChecking]);

    return projectFleetMap;
};
