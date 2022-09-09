import { ITableColumn } from 'components/Table/types';

const columns: ITableColumn[] = [
    {
        name: 'region',
        title: 'Region',
        type: 'text',
        width: 150,
    },
    {
        name: 'instance_type',
        title: 'Instance type',
        type: 'text',
        width: 120,
    },
    {
        name: 'resources',
        title: 'Resources',
        type: 'text',
        width: 230,
    },
    {
        name: 'purchase_type',
        title: 'Purchase type',
        type: 'text',
        width: 120,
    },
    {
        hidden: true,
        name: 'estimated_price',
        title: 'Estimated price',
        type: 'text',
        width: 120,
    },
    {
        name: 'maximum',
        title: 'Maximum',
        type: 'text',
        width: 90,
    },
    {
        name: 'in_use',
        title: 'Status',
        type: 'text',
        width: 150,
    },
];

export default columns;
