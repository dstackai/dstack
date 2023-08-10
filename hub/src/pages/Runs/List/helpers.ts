import { groupBy as _groupBy } from 'lodash';

export const getGroupedRunsByProjectAndRepoID = (runs: IRunListItem[]) => {
    return _groupBy(runs, ({ project, repo_id }) => `${project}/${repo_id}`);
};
