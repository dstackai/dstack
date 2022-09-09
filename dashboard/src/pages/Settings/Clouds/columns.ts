import { ITableColumn } from 'components/Table/types';

const columns: ITableColumn[] = [
    {
        name: 'cloud',
        title: 'Cloud',
        type: 'empty',
        width: 60,
    },
    {
        name: 'accessKey',
        title: 'Access key',
        type: 'text',
        width: 200,
    },
    {
        name: 'secretKey',
        title: 'Secret key',
        type: 'text',
        width: 300,
    },
    {
        name: 'region',
        title: 'Region',
        type: 'text',
        width: 170,
    },
    {
        name: 'artifactBucket',
        title: 'Artifact S3 bucket',
        type: 'text',
        width: 190,
    },
];

export default columns;
