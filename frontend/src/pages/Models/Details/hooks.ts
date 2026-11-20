import { useMemo } from 'react';

import { useAppSelector } from 'hooks';

import { selectUserData } from 'App/slice';

import { mergeModels } from '../helpers';
import { useProjectsImports, useRunModels } from '../hooks';
import { hasModelMetering } from './helpers';

/**
 * Loads the model that `projectName` runs as `modelName`: the project's own model or one that the user's projects import.
 */
export const useModel = (projectName: IProject['project_name'], modelName: IModel['name']) => {
    const userData = useAppSelector(selectUserData);

    // A project's own model comes from an active run or, when no active run has it, from the project's latest runs
    const runModels = useRunModels(
        { project_name: projectName },
        (activeModels) => !!activeModels && !activeModels.some(({ name }) => name === modelName),
    );

    // The model's endpoints come from the import lists of all the user's projects
    const imports = useProjectsImports();

    const isLoading = runModels.isFetching || imports.isFetching;
    const error = isLoading ? undefined : (runModels.error ?? imports.error);

    const model = useMemo(() => {
        if (isLoading || error) {
            return;
        }

        return mergeModels(runModels.models, imports.projectsImports).find(
            (model) => model.project_name === projectName && model.name === modelName,
        );
    }, [isLoading, error, runModels.models, imports.projectsImports, projectName, modelName]);

    return {
        model,
        isLoading,
        error,
        // Not while a request runs, and not when one has failed
        isNotFound: !isLoading && !error && !model,
        hasMetering: !!model && hasModelMetering(model, imports.projects, userData),
        // The user's projects and their import lists, for the Exports tab
        projects: imports.projects,
        projectsImports: imports.projectsImports,
    } as const;
};
