import { groupBy as _groupBy } from 'lodash';

export const getGroupedRunsByProjectAndRepoID = (runs: IRun[]) => {
    return _groupBy(runs, ({ project_name, id }) => `${project_name}/${id}`);
};
