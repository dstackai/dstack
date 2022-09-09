import {
    filterRuns,
    isFinished,
    isAvailableResumeFor,
    findRunByName,
    filterRunsByRunNameArray,
    filterWorkflowByWorkflowNamesSet,
    getTaggedCount,
    filterRunByQuery,
    filterDataByTagName,
    filterVariableByQuery,
    filterWorkflows,
    getRunWorkflowFullName,
    workflowsGroupByRunName,
    parseRunWorkflowFullName,
    isFailed,
} from './run';

const workflows: IRunWorkflow[] = [
    {
        user_name: 'peterschmidt85',
        run_name: 'white-mayfly-1',
        tag_name: null,
        repo_url: 'https://github.com/dstackai/gpt-2.git',
        repo_branch: 'finetuning',
        repo_hash: '89184a72ea8443c3c3c42f095ad89ee168b40f19',
        variables: {
            batch_size: '2',
            model: '117M',
            learning_rate: '0.00003',
        },
        workflow_name: 'train-mnist',
        submitted_at: 1652081291000,
        updated_at: 1652081544156,
        status: 'failed',
        artifact_paths: ['peterschmidt85/white-mayfly-1/c04456adc157/model'],
        ports: [],
        availability_issues: [],
        repo_diff: '',
        appsModal: [],
    },
    {
        user_name: 'peterschmidt85',
        run_name: 'good-snake-1',
        tag_name: null,
        repo_url: 'https://github.com/dstackai/gpt-2.git',
        repo_branch: 'finetuning',
        repo_hash: '89184a72ea8443c3c3c42f095ad89ee168b40f19',
        variables: {
            batch_size: '2',
            model: '117M',
            learning_rate: '0.00003',
        },
        workflow_name: 'download-mnist',
        submitted_at: 1651844925652,
        updated_at: 1651845015863,
        status: 'done',
        artifact_paths: ['peterschmidt85/good-snake-1/baf30e3a646f/data'],
        ports: [],
        availability_issues: [],
        repo_diff: '',
        appsModal: [],
    },
    {
        user_name: 'peterschmidt85',
        run_name: 'good-snake-1',
        tag_name: null,
        repo_url: 'https://github.com/dstackai/gpt-2.git',
        repo_branch: 'finetuning',
        repo_hash: '89184a72ea8443c3c3c42f095ad89ee168b40f19',
        variables: {
            batch_size: '2',
            model: '117M',
            learning_rate: '0.00003',
        },
        workflow_name: 'jupyter',
        submitted_at: 1651844942573,
        updated_at: 1651845639209,
        status: 'stopped',
        artifact_paths: [],
        ports: [],
        availability_issues: [],
        repo_diff: '',
        appsModal: [],
    },
    {
        user_name: 'peterschmidt85',
        run_name: 'soft-owl-1',
        tag_name: null,
        repo_url: 'https://github.com/dstackai/gpt-2.git',
        repo_branch: 'finetuning',
        repo_hash: '89184a72ea8443c3c3c42f095ad89ee168b40f19',
        variables: {
            batch_size: '2',
            model: '117M',
            learning_rate: '0.00003',
        },
        workflow_name: 'download-mnist',
        submitted_at: 1651844562007,
        updated_at: 1651844879483,
        status: 'done',
        artifact_paths: ['peterschmidt85/soft-owl-1/9acf8b2d156f/data'],
        ports: [],
        availability_issues: [],
        repo_diff: '',
        appsModal: [],
    },
    {
        user_name: 'peterschmidt85',
        run_name: 'soft-owl-1',
        tag_name: 'test-tag',
        repo_url: 'https://github.com/dstackai/gpt-2.git',
        repo_branch: 'finetuning',
        repo_hash: '89184a72ea8443c3c3c42f095ad89ee168b40f19',
        variables: {
            batch_size: '2',
            model: '117M',
            learning_rate: '0.00003',
        },
        workflow_name: 'train-mnist',
        submitted_at: 1651844582979,
        updated_at: 1651845250666,
        status: 'done',
        artifact_paths: ['peterschmidt85/soft-owl-1/4bec8fcbc697/model'],
        ports: [],
        availability_issues: [],
        repo_diff: '',
        appsModal: [],
    },
];

const runs: IRun[] = [
    {
        user_name: 'olgenn',
        run_name: 'tame-dodo-1',
        workflow_name: 'finetune-model',
        repo_url: 'https://github.com/dstackai/gpt-2.git',
        repo_branch: 'finetuning',
        repo_hash: '89184a72ea8443c3c3c42f095ad89ee168b40f19',
        repo_diff: null,
        variables: {
            batch_size: '2',
            model: '117M',
            learning_rate: '0.00003',
        },
        submitted_at: 1643698923010,
        started_at: 1643699248450,
        finished_at: null,
        status: 'stopped',
        runner_id: '09aea601-045b-4c0e-ade3-a5fccd806628',
        runner_user_name: null,
        runner_name: 'stale-puma-1',
        updated_at: 1644262048012,
        tag_name: 'olgenn',
        number_of_finished_jobs: 0,
        number_of_unfinished_jobs: 0,
    },
    {
        user_name: 'olgenn',
        run_name: 'tame-dodo-2',
        workflow_name: 'finetune-model-2',
        repo_url: 'https://github.com/dstackai/gpt-3.git',
        repo_branch: 'dev',
        repo_hash: '89184a72ea8443c3c3c42f095ad89ee168b40f10',
        repo_diff: null,
        variables: {
            batch_size: '2',
            model: '118M',
            learning_rate: '0.00003',
        },
        submitted_at: 1643698923010,
        started_at: 1643699248450,
        finished_at: null,
        status: 'running',
        runner_id: '09aea601-045b-4c0e-ade3-a5fccd806628',
        runner_user_name: null,
        runner_name: 'stale-puma-2',
        updated_at: 1644262048012,
        tag_name: 'tag-1',
        number_of_finished_jobs: 0,
        number_of_unfinished_jobs: 0,
    },
    {
        user_name: 'olgenn',
        run_name: 'tame-dodo-3',
        workflow_name: 'finetune-model-3',
        repo_url: 'https://github.com/dstackai/gpt-4.git',
        repo_branch: 'dev',
        repo_hash: '89184a72ea8443c3c3c42f095ad89ee168b40f11',
        repo_diff: null,
        variables: {
            batch_size: '2',
            model: '119M',
            learning_rate: '0.00003',
        },
        submitted_at: 1643698923010,
        started_at: 1643699248450,
        finished_at: null,
        status: 'failed',
        runner_id: '09aea601-045b-4c0e-ade3-a5fccd806628',
        runner_user_name: null,
        runner_name: 'stale-puma-3',
        updated_at: 1644262048012,
        tag_name: 'tag-2',
        number_of_finished_jobs: 0,
        number_of_unfinished_jobs: 0,
    },
];

describe('Test run libs', () => {
    test('check is finished run', () => {
        expect(isFinished(runs[0])).toBeTruthy();
        expect(isFinished(runs[1])).toBeFalsy();
        expect(isFinished(runs[2])).toBeTruthy();
    });

    test('check is available resume for run', () => {
        expect(isAvailableResumeFor(runs[0])).toBeTruthy();
        expect(isAvailableResumeFor(runs[1])).toBeFalsy();
        expect(isAvailableResumeFor(runs[2])).toBeFalsy();
    });

    test('check is available resume for run', () => {
        expect(findRunByName(runs, runs[0].run_name)).toEqual(runs[0]);
        expect(findRunByName(runs, runs[2].run_name)).toEqual(runs[2]);
        expect(findRunByName(runs, 'testTest')).toBe(undefined);
    });

    test('filter run by query', () => {
        const run = runs[0];

        expect(filterRunByQuery(run, 'tame-dodo')).toBeTruthy();
        expect(filterRunByQuery(run, 'tame-dodo-1')).toBeTruthy();
        expect(filterRunByQuery(run, 'tame-dodo-2')).toBeFalsy();

        expect(filterRunByQuery(run, 'olg')).toBeTruthy();
        expect(filterRunByQuery(run, 'olgenn')).toBeTruthy();
        expect(filterRunByQuery(run, 'olgenn-99')).toBeFalsy();

        expect(filterRunByQuery(run, 'finetune-mo')).toBeTruthy();
        expect(filterRunByQuery(run, 'finetune-model')).toBeTruthy();
        expect(filterRunByQuery(run, 'finetune-model-99')).toBeFalsy();

        expect(filterRunByQuery(run, 'stale-puma')).toBeTruthy();
        expect(filterRunByQuery(run, 'stale-puma-1')).toBeTruthy();
        expect(filterRunByQuery(run, 'stale-puma-99')).toBeFalsy();
    });

    test('filter variable by query', () => {
        const variable: IVariable = {
            key: 'model',
            value: '118M',
        };

        expect(filterVariableByQuery(variable, 'model')).toBeTruthy();
        expect(filterVariableByQuery(variable, 'Model')).toBeTruthy();
        expect(filterVariableByQuery(variable, 'oDe')).toBeTruthy();

        expect(filterVariableByQuery(variable, '118M')).toBeTruthy();
        expect(filterVariableByQuery(variable, '118m')).toBeTruthy();
        expect(filterVariableByQuery(variable, '18m')).toBeTruthy();

        expect(filterVariableByQuery(variable, 'model-asd')).toBeFalsy();
        expect(filterVariableByQuery(variable, '118M-asd')).toBeFalsy();
    });

    test('filter run by tag name', () => {
        const run = runs[0];

        expect(filterDataByTagName(run, 'olg')).toBeFalsy();
        expect(filterDataByTagName(run, 'olgenn-99')).toBeFalsy();
        expect(filterDataByTagName(run, 'Olgenn')).toBeFalsy();
        expect(filterDataByTagName(run, 'olgenn')).toBeTruthy();
    });

    test('filter runs', () => {
        expect(filterRuns(runs, 'tame-dodo')).toEqual(runs);
        expect(filterRuns(runs, 'finetune-model-2')).toEqual([runs[1]]);
        expect(filterRuns(runs, 'FInetune-model-2')).toEqual([runs[1]]);
        expect(filterRuns(runs, 'stale-puma-3')).toEqual([runs[2]]);
        expect(filterRuns(runs, 'stale-puma-3')).toEqual([runs[2]]);
        expect(filterRuns(runs, 'tag-')).toEqual([runs[1], runs[2]]);
        expect(filterRuns(runs, 'batch_size')).toEqual(runs);
        expect(filterRuns(runs, '118M')).toEqual([runs[1]]);
        expect(filterRuns(runs, 'asdasdasd')).toEqual([]);
    });

    test('filter workflows', () => {
        expect(filterWorkflows(workflows, 'white-mayfly-1')).toEqual([workflows[0]]);
        expect(filterWorkflows(workflows, 'good-snake-1')).toEqual([workflows[1], workflows[2]]);
        expect(filterWorkflows(workflows, 'train-mnist')).toEqual([workflows[0], workflows[4]]);
        expect(filterWorkflows(workflows, 'test-tag')).toEqual([workflows[4]]);
        expect(filterWorkflows(workflows, 'asdasdasd')).toEqual([]);
    });

    test('filter runs by run names array', () => {
        expect(filterRunsByRunNameArray(runs, ['tame-dodo-1', 'tame-dodo-2'])).toEqual([runs[0], runs[1]]);
        expect(filterRunsByRunNameArray(runs, ['tame-dodo-3', 'tame-dodo-2'])).toEqual([runs[1], runs[2]]);
        expect(filterRunsByRunNameArray(runs, ['tame-dodo-1'])).toEqual([runs[0]]);
    });

    test('workflows group by run name', () => {
        expect(workflowsGroupByRunName(workflows)).toEqual([
            ['white-mayfly-1', [workflows[0]]],
            ['good-snake-1', [workflows[1], workflows[2]]],
            ['soft-owl-1', [workflows[3], workflows[4]]],
        ]);
    });

    test('get run workflow full name', () => {
        expect(getRunWorkflowFullName(workflows[0])).toBe('peterschmidt85/white-mayfly-1/train-mnist');
        expect(getRunWorkflowFullName(workflows[1])).toBe('peterschmidt85/good-snake-1/download-mnist');
        expect(getRunWorkflowFullName(workflows[4])).toBe('peterschmidt85/soft-owl-1/train-mnist');
    });

    test('parse run workflow full name', () => {
        expect(parseRunWorkflowFullName('peterschmidt85/white-mayfly-1/train-mnist')).toEqual({
            user_name: workflows[0].user_name,
            run_name: workflows[0].run_name,
            workflow_name: workflows[0].workflow_name,
        });
        expect(parseRunWorkflowFullName('peterschmidt85/good-snake-1/download-mnist')).toEqual({
            user_name: workflows[1].user_name,
            run_name: workflows[1].run_name,
            workflow_name: workflows[1].workflow_name,
        });
    });

    test('filter runs by run names set', () => {
        expect(filterWorkflowByWorkflowNamesSet(workflows, new Set(['peterschmidt85/white-mayfly-1/train-mnist']))).toEqual([
            workflows[0],
        ]);
        expect(filterWorkflowByWorkflowNamesSet(workflows, new Set(['peterschmidt85/good-snake-1/download-mnist']))).toEqual([
            workflows[1],
        ]);
        expect(
            filterWorkflowByWorkflowNamesSet(
                workflows,
                new Set(['peterschmidt85/good-snake-1/download-mnist', 'peterschmidt85/soft-owl-1/train-mnist']),
            ),
        ).toEqual([workflows[1], workflows[4]]);
    });

    test('get tagged runs count', () => {
        expect(getTaggedCount(runs)).toBe(3);
        expect(getTaggedCount([])).toBe(0);
    });

    test('is failed run or workflow', () => {
        expect(isFailed(runs[0])).toBe(false);
        expect(isFailed(runs[1])).toBe(false);
        expect(isFailed(runs[2])).toBe(true);
    });
});
