import { GlobalUserRole } from 'types';

import { getProjectRoleByUserName } from 'pages/Project/utils';

import { IModelExtended } from '../../List/types';

export type TModelExportProject = {
    export_name: IExport['name'];
    // The project that imports the model
    project_name: IProject['project_name'];
};

export type TModelExport = {
    export_name: IExport['name'];
    // The projects that import the model through the export
    projects: TModelExportProject[];
};

/**
 * A project's exports are for its members and for global admins.
 */
export const canListModelExports = (model: IModelExtended, projects: IProject[], user: IUser | null): boolean => {
    if (!user) {
        return false;
    }

    if (user.global_role === GlobalUserRole.ADMIN) {
        return true;
    }

    return projects.some(
        (project) => project.project_name === model.project_name && getProjectRoleByUserName(project, user.username) !== null,
    );
};

/**
 * The model's exports, each with the projects that import the model through it. `exports` are the exports of
 * the model's project, which its members see, so they get every export and project. Other users get the exports
 * that their own projects import the model through, from their import lists.
 */
export const getModelExports = (
    model: IModelExtended,
    exports: IExport[] | undefined,
    projectsImports: TProjectImports[],
): TModelExport[] => {
    const hasModel = ({ exported_models }: { exported_models: { name: string }[] }) =>
        exported_models.some(({ name }) => name === model.name);

    const projectNames = new Map<TModelExport['export_name'], TModelExportProject['project_name'][]>();

    if (exports) {
        exports.filter(hasModel).forEach(({ name, imports }) =>
            projectNames.set(
                name,
                imports.map(({ project_name }) => project_name),
            ),
        );
    } else {
        projectsImports.forEach(({ project_name, imports }) =>
            imports
                .filter((item) => item.export.project_name === model.project_name && hasModel(item.export))
                .forEach((item) =>
                    projectNames.set(item.export.name, [...(projectNames.get(item.export.name) ?? []), project_name]),
                ),
        );
    }

    return Array.from(projectNames)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([export_name, names]) => ({
            export_name,
            projects: names.sort((a, b) => a.localeCompare(b)).map((project_name) => ({ export_name, project_name })),
        }));
};
