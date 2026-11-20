import { groupBy as _groupBy, uniqBy as _uniqBy } from 'lodash';

import { isValidUrl } from 'libs';

import { finishedJobs } from 'pages/Runs/constants';

import { IModelEndpoint, IModelExtended } from './List/types';

export const getModelGateway = (baseUrl?: IModelEndpoint['base_url']) => {
    if (!baseUrl) {
        return '';
    }

    if (isValidUrl(baseUrl)) {
        return baseUrl;
    }

    return document.location.origin + baseUrl;
};

/**
 * Merges the models of runs and the models that the user's projects import, so that a model shows once.
 * A model is the project that runs it and its name. It takes the first of its runs that isn't finished, else its latest run:
 * `models` have the latest run first. It takes an endpoint from each of the user's projects that has it.
 */
export const mergeModels = (models: IModelExtended[], projectsImports: TProjectImports[]): IModelExtended[] => {
    const importedModels = projectsImports.flatMap(({ project_name, imports }) =>
        imports.flatMap(({ export: { project_name: exportProjectName, exported_models } }) =>
            exported_models.map(
                ({ name, base_url }): IModelExtended => ({
                    name,
                    project_name: exportProjectName,
                    endpoints: [{ project_name, base_url }],
                }),
            ),
        ),
    );

    const modelGroups = _groupBy([...models, ...importedModels], ({ project_name, name }) => `${project_name}/${name}`);

    return Object.values(modelGroups).map((sameModels) => {
        // A finished run has the status of its latest job submission
        const model = sameModels.find(({ run }) => run && !finishedJobs.includes(run.status)) ?? sameModels[0];

        return {
            ...model,
            endpoints: _uniqBy(
                [model, ...sameModels].flatMap(({ endpoints }) => endpoints),
                'project_name',
            ),
        };
    });
};

/**
 * An importer can't see the exporter's run. Its import list gives the model a URL while a service serves it.
 */
export const getImportedModelStatus = (model: IModelExtended): 'running' | 'stopped' =>
    model.endpoints.some(({ base_url }) => base_url) ? 'running' : 'stopped';

/**
 * A model answers requests while a service serves it: a project's own model until its run is finished,
 * an imported one while its import list gives it a URL. A model that isn't served keeps the URL of its last run.
 */
export const isModelServed = (model: IModelExtended): boolean =>
    model.run ? !finishedJobs.includes(model.run.status) : getImportedModelStatus(model) === 'running';
