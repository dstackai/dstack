import { getExtendedModelFromRun } from './run';

const BASE_URL = 'https://gateway.example.com/exporter-proj';

const makeRun = (status: IRun['status']) =>
    ({
        id: 'run-id',
        project_name: 'exporter-proj',
        user: 'alice',
        submitted_at: '2026-12-03T09:02:00+00:00',
        status,
        run_spec: { run_name: 'qwen-service' },
        service: {
            url: '/proxy/services/exporter-proj/qwen-service/',
            model: { name: 'Qwen/Qwen3.6-27B-FP8', type: 'chat', base_url: BASE_URL },
        },
    }) as IRun;

describe('Model of a run', () => {
    test.each(['running', 'terminated'] as const)('the model of a %s run has the URL of the run', (status) => {
        const model = getExtendedModelFromRun(makeRun(status));

        expect(model?.endpoints).toEqual([{ project_name: 'exporter-proj', base_url: BASE_URL }]);
    });
});
