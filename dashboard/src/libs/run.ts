import { isFinishedStatus, isAvailableResumeByStatus, isFailedStatus } from './status';

export const filterRunByQuery = (run: IRun, queryString: string): boolean => {
    const query = queryString.toLowerCase();

    return (
        run.run_name.toLowerCase().indexOf(query) > -1 ||
        (run.runner_name && run.runner_name.toLowerCase().indexOf(query) > -1) ||
        (run.workflow_name && run.workflow_name.toLowerCase().indexOf(query) > -1) ||
        (run.tag_name && run.tag_name.toLowerCase().indexOf(query) > -1) ||
        Object.keys(run.variables).some(
            (key) => key.toLowerCase().indexOf(query) > -1 || run.variables[key].toLowerCase().indexOf(query) > -1,
        )
    );
};

export const filterRunWorkflowByQuery = (workflow: IRunWorkflow, queryString: string): boolean => {
    const query = queryString.toLowerCase();

    return (
        workflow.run_name.toLowerCase().indexOf(query) > -1 ||
        (workflow.workflow_name && workflow.workflow_name.toLowerCase().indexOf(query) > -1) ||
        (!!workflow.tag_name && workflow.tag_name.toLowerCase().indexOf(query) > -1)
    );
};

export const filterVariableByQuery = (variable: IVariable, queryString: string): boolean => {
    const query = queryString.toLowerCase();

    return variable.key.toLowerCase().indexOf(query) > -1 || variable.value.toLowerCase().indexOf(query) > -1;
};

export const filterDataByTagName = (run: { tag_name: null | string }, tag: string): boolean => {
    return run.tag_name === tag;
};

export const filterRuns = (runs: IRun[], query: string): IRun[] => {
    return runs.filter((run) => filterRunByQuery(run, query));
};

export const filterWorkflows = (workflows: IRunWorkflow[], query: string): IRunWorkflow[] => {
    return workflows.filter((workflow) => filterRunWorkflowByQuery(workflow, query));
};

export const isFinished = (run: IRun | IRunWorkflow): boolean => {
    return isFinishedStatus(run.status);
};

export const isFailed = (item: IRun | IRunWorkflow): boolean => {
    return isFailedStatus(item.status);
};

export const isAvailableResumeFor = (run: IRun | IRunWorkflow): boolean => {
    return isAvailableResumeByStatus(run.status);
};

export const findRunByName = (runs: IRun[], runName: IRun['run_name']): IRun | undefined => {
    return runs.find((r) => r.run_name === runName);
};

export const filterRunsByRunNameArray = (runs: Array<IRun>, runNames: Array<IRun['run_name']>): IRun[] => {
    const set = new Set<IRun['run_name']>(runNames);
    return runs.filter((r) => set.has(r.run_name));
};

export const workflowsGroupByRunName = (workflows: IRunWorkflow[]): WorkflowGroupByRunName => {
    return workflows.reduce((result, workflow) => {
        // const array = result.get(workflow.run_name);
        const index = result.findIndex(([runName]) => runName === workflow.run_name);

        if (index >= 0) result[index][1].push(workflow);
        else result.push([workflow.run_name, [workflow]]);

        return result;
    }, [] as WorkflowGroupByRunName);
};

type RunWorkflowFullName = string;

export const getRunWorkflowFullName = (workflow: IRunWorkflow): RunWorkflowFullName => {
    if (!workflow.workflow_name) return `${workflow.user_name}/${workflow.run_name}`;
    return `${workflow.user_name}/${workflow.run_name}/${workflow.workflow_name}`;
};

export const parseRunWorkflowFullName = (workflowFullName: RunWorkflowFullName) => {
    const [user_name, run_name, workflow_name] = workflowFullName.split('/');

    return { user_name, run_name, workflow_name };
};

export const filterWorkflowByWorkflowNamesSet = (
    workflows: Array<IRunWorkflow>,
    workflowNames: Set<string>,
): IRunWorkflow[] => {
    return workflows.filter((w) => workflowNames.has(getRunWorkflowFullName(w)));
};

export const getTaggedCount = (items: Array<IRun | IRunWorkflow>): number => {
    return items.reduce((result, item) => {
        if (item.tag_name) ++result;
        return result;
    }, 0);
};
