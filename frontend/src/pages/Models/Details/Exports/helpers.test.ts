import { GlobalUserRole } from 'types';

import { canListModelExports, getModelExports } from './helpers';

import { IModelExtended } from '../../List/types';

// exporter-proj runs the model
const model: IModelExtended = { name: 'Qwen/Qwen3.8-Flash-Next', project_name: 'exporter-proj', endpoints: [] };

const makeExport = (name: string, projectNames: string[], modelNames: string[]): IExport => ({
    name,
    imports: projectNames.map((project_name) => ({ project_name })),
    exported_models: modelNames.map((modelName) => ({ name: modelName })),
});

const makeImports = (projectName: string, exportProjectName: string, exportName: string, modelNames: string[]) => ({
    project_name: projectName,
    imports: [
        {
            export: {
                name: exportName,
                project_name: exportProjectName,
                exported_models: modelNames.map((name) => ({ name, base_url: null })),
            },
        },
    ],
});

const makeUser = (globalRole: TUserRole) => ({ username: 'bob', global_role: globalRole }) as IUser;

const makeProject = (projectName: string, userNames: string[]) =>
    ({
        project_name: projectName,
        members: userNames.map((username) => ({ user: { username }, project_role: 'user' })),
    }) as IProject;

describe('Model exports', () => {
    test("a member of the model's project gets every export of the model, with the projects that import it", () => {
        const exports = [
            makeExport('importer2-models', ['importer2-proj'], [model.name]),
            makeExport('importer-models', ['importer-proj', 'another-proj'], [model.name, 'other-model']),
            makeExport('other-models', ['importer-proj'], ['other-model']),
            makeExport('new-models', [], [model.name]),
        ];

        expect(getModelExports(model, exports, [])).toEqual([
            {
                export_name: 'importer-models',
                projects: [
                    { export_name: 'importer-models', project_name: 'another-proj' },
                    { export_name: 'importer-models', project_name: 'importer-proj' },
                ],
            },
            {
                export_name: 'importer2-models',
                projects: [{ export_name: 'importer2-models', project_name: 'importer2-proj' }],
            },
            { export_name: 'new-models', projects: [] },
        ]);
    });

    test("other users get the exports that their own projects import the model through, from the model's project", () => {
        const projectsImports = [
            makeImports('importer-proj', 'exporter-proj', 'importer-models', [model.name]),
            // A model of the same name that another project exports
            makeImports('importer2-proj', 'other-proj', 'other-models', [model.name]),
            makeImports('importer3-proj', 'exporter-proj', 'other-models', ['other-model']),
            makeImports('another-proj', 'exporter-proj', 'importer-models', [model.name]),
        ];

        expect(getModelExports(model, undefined, projectsImports)).toEqual([
            {
                export_name: 'importer-models',
                projects: [
                    { export_name: 'importer-models', project_name: 'another-proj' },
                    { export_name: 'importer-models', project_name: 'importer-proj' },
                ],
            },
        ]);
    });

    test("the exports of the model's project are for its members and for global admins", () => {
        const projects = [makeProject('exporter-proj', ['alice']), makeProject('importer-proj', ['bob'])];

        expect(canListModelExports(model, projects, makeUser(GlobalUserRole.USER))).toBe(false);
        expect(canListModelExports(model, projects, makeUser(GlobalUserRole.ADMIN))).toBe(true);
        expect(canListModelExports(model, [makeProject('exporter-proj', ['bob'])], makeUser(GlobalUserRole.USER))).toBe(true);
        expect(canListModelExports(model, projects, null)).toBe(false);
    });
});
