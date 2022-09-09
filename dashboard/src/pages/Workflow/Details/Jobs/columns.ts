import { ITableColumn } from 'components/Table/types';

const columns: ITableColumn[] = [
    {
        name: 'job',
        title: 'Job',
        type: 'link',
        width: 150,
    },
    {
        name: 'status',
        title: 'Status',
        type: 'text',
        width: 100,
    },
    {
        name: 'date',
        title: 'Submitted',
        type: 'text',
        width: 150,
    },
    {
        name: 'variables',
        title: 'Variables',
        type: 'text',
        width: 160,
    },
    {
        name: 'artifacts',
        title: 'Artifacts',
        type: 'artifacts',
        width: 160,
    },
    {
        name: 'runner',
        title: 'Runner',
        type: 'text',
        width: 140,
    },
];

export default columns;
