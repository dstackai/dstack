import { useMemo } from 'react';

import { useAppSelector } from 'hooks';
import { useGetProjectExportsQuery } from 'services/export';

import { selectUserData } from 'App/slice';

import { canListModelExports, getModelExports } from './helpers';

import { IModelExtended } from '../../List/types';

/**
 * Loads the model's exports and the projects that import the model through them, as far as the user can see
 * them. The user's projects and their import lists come from the page, which has loaded them for the model.
 */
export const useModelExports = (model: IModelExtended, projects: IProject[], projectsImports: TProjectImports[]) => {
    const userData = useAppSelector(selectUserData);

    const canListExports = canListModelExports(model, projects, userData);

    const { currentData, isFetching, error } = useGetProjectExportsQuery(
        { project_name: model.project_name },
        { skip: !canListExports },
    );

    const modelExports = useMemo(() => {
        if (isFetching || error) {
            return [];
        }

        return getModelExports(model, canListExports ? currentData : undefined, projectsImports);
    }, [isFetching, error, model, canListExports, currentData, projectsImports]);

    return { modelExports, isLoading: isFetching, error } as const;
};
