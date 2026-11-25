import { useMemo } from 'react';
import { product } from 'product';

import { useAppSelector } from 'hooks';
import { useGetProjectsImportsQuery } from 'services/import';
import { useGetProjectsQuery } from 'services/project';
import { useGetModelsQuery } from 'services/run';

import { selectUserName } from 'App/slice';

import { IModelExtended, TModelsFilters } from './List/types';

/**
 * Loads the models of runs: of every active run and, where `needsLatestRuns` says so, of the latest runs too.
 * The latest runs have the models that no active run has, the stopped ones.
 * `needsLatestRuns` gets the models of the active runs once they are loaded.
 */
export const useRunModels = (filters: TModelsFilters, needsLatestRuns: (activeModels?: IModelExtended[]) => boolean) => {
    const activeQuery = useGetModelsQuery({ ...filters, only_active: true });
    const activeModels = activeQuery.isFetching ? undefined : activeQuery.currentData;
    const latestQuery = useGetModelsQuery(filters, { skip: !needsLatestRuns(activeModels) });

    const models = useMemo(
        () => [...(activeQuery.currentData ?? []), ...(latestQuery.currentData ?? [])],
        [activeQuery.currentData, latestQuery.currentData],
    );

    const refetch = () => {
        activeQuery.refetch();

        // A skipped query can't be refetched
        if (!latestQuery.isUninitialized) {
            latestQuery.refetch();
        }
    };

    return {
        models,
        isFetching: activeQuery.isFetching || latestQuery.isFetching,
        error: activeQuery.error ?? latestQuery.error,
        refetch,
    } as const;
};

/**
 * Loads the import lists of the user's projects, or of the project of the filter alone.
 * An imported model has no user, so a filter by user leaves the imported models out.
 * Exports exist only where the server enables them. Elsewhere there are no imports, and nothing is requested.
 */
export const useProjectsImports = (filters: TModelsFilters = {}) => {
    const userName = useAppSelector(selectUserName);
    const skip = !product.hasExports || !!filters.username;

    const projectsQuery = useGetProjectsQuery(
        { username: userName ?? '' },
        { skip: skip || !!filters.project_name || !userName },
    );

    const projects = projectsQuery.currentData?.data;
    const projectNames = filters.project_name ? [filters.project_name] : projects?.map(({ project_name }) => project_name);

    const importsQuery = useGetProjectsImportsQuery({ project_names: projectNames ?? [] }, { skip: skip || !projectNames });

    const refetch = () => {
        // A skipped query can't be refetched
        if (!importsQuery.isUninitialized) {
            importsQuery.refetch();
        }
    };

    return {
        projects: projects ?? [],
        projectsImports: importsQuery.currentData ?? [],
        // The projects list is asked by the user's name, so it waits for the name
        isFetching: !skip && (projectsQuery.isFetching || importsQuery.isFetching || (!filters.project_name && !userName)),
        error: projectsQuery.error,
        refetch,
    } as const;
};
