import { getImportedModelStatus, isModelServed, mergeModels } from './helpers';

import { IModelExtended } from './List/types';

const QWEN = 'Qwen/Qwen3.6-27B-FP8';

const getUrl = (projectName: string) => `https://gateway.example.com/${projectName}`;

const makeModel = (projectName: string): IModelExtended => ({
    name: QWEN,
    project_name: projectName,
    endpoints: [{ project_name: projectName, base_url: getUrl(projectName) }],
    run: {
        id: `${projectName}-run-id`,
        run_name: 'qwen-service',
        status: 'running',
        status_message: 'Running',
        submitted_at: '2026-12-03T09:02:00+00:00',
        user: 'alice',
        resources: null,
        price: null,
        repository: null,
        backend: null,
    },
});

const makeProjectImports = (projectName: string, baseUrl: string | null = getUrl(projectName)): TProjectImports => ({
    project_name: projectName,
    imports: [
        { export: { name: 'models', project_name: 'exporter-proj', exported_models: [{ name: QWEN, base_url: baseUrl }] } },
    ],
});

describe('Models helpers', () => {
    test("a model that two of the user's projects import is one row", () => {
        const models = mergeModels([], [makeProjectImports('importer-proj'), makeProjectImports('importer2-proj')]);

        expect(models).toEqual([
            {
                name: QWEN,
                project_name: 'exporter-proj',
                endpoints: [
                    { project_name: 'importer-proj', base_url: getUrl('importer-proj') },
                    { project_name: 'importer2-proj', base_url: getUrl('importer2-proj') },
                ],
            },
        ]);
    });

    test('an imported model joins the row of its run, and a model of another project with the same name does not', () => {
        const models = mergeModels(
            [makeModel('exporter-proj'), makeModel('other-proj')],
            [makeProjectImports('importer-proj')],
        );

        expect(models.map(({ project_name, run }) => [project_name, run?.id])).toEqual([
            ['exporter-proj', 'exporter-proj-run-id'],
            ['other-proj', 'other-proj-run-id'],
        ]);
        expect(models[0].endpoints.map(({ project_name }) => project_name)).toEqual(['exporter-proj', 'importer-proj']);
        expect(models[1].endpoints.map(({ project_name }) => project_name)).toEqual(['other-proj']);
    });

    test('a model takes its run that is not finished, though a later run of it has finished', () => {
        const running = makeModel('exporter-proj');

        const makeFinishedModel = (runId: string): IModelExtended => ({
            ...running,
            run: running.run && { ...running.run, id: runId, status: 'terminated' },
        });

        // The latest run first
        const [later, earlier] = [makeFinishedModel('later-run-id'), makeFinishedModel('earlier-run-id')];

        expect(mergeModels([later, running], [])).toEqual([running]);
        expect(mergeModels([later, earlier], [])).toEqual([later]);
    });

    test("a project's own model is served until its run is finished, and keeps its URL afterwards", () => {
        const running = makeModel('exporter-proj');
        const stopped: IModelExtended = { ...running, run: running.run && { ...running.run, status: 'terminated' } };

        expect(isModelServed(running)).toBe(true);
        expect(isModelServed(stopped)).toBe(false);
        expect(stopped.endpoints[0].base_url).toBe(getUrl('exporter-proj'));
    });

    test('an imported model is served while its import list gives it a URL', () => {
        const [running] = mergeModels([], [makeProjectImports('importer-proj')]);
        const [stopped] = mergeModels([], [makeProjectImports('importer-proj', null)]);

        expect(isModelServed(running)).toBe(true);
        expect(isModelServed(stopped)).toBe(false);
    });

    test('an imported model is running with a URL and stopped without one', () => {
        const [running] = mergeModels([], [makeProjectImports('importer-proj')]);
        const [stopped] = mergeModels([], [makeProjectImports('importer-proj', null)]);

        expect(getImportedModelStatus(running)).toBe('running');
        expect(getImportedModelStatus(stopped)).toBe('stopped');
    });
});
