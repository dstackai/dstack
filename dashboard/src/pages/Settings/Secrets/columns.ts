import { ITableColumn } from 'components/Table/types';

const columns: ITableColumn[] = [
    {
        name: 'secret_name',
        title: 'Key',
        type: 'text',
        width: 155,
    },
    {
        name: 'secret_value',
        title: 'Value',
        type: 'text',
        width: 185,
    },
];

export default columns;
