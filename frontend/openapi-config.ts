import { intersectionWith } from 'lodash';
import type { ConfigFile } from '@rtk-query/codegen-openapi';

import type { OperationDefinition } from '@rtk-query/codegen-openapi/src/types';

const filterEndpoint =
    (tags: string[]) =>
    (_, { operation }: OperationDefinition) => {
        const test = (a: string, b: string) => a.toLowerCase().includes(b.toLowerCase());

        return Boolean(intersectionWith(operation.tags as string[], tags, test).length);
    };

const FILES = {
    './src/api-services/userPayments.ts': {
        filterEndpoints: filterEndpoint(['user_payments']),
        exportName: 'userPayments',
    },
};

const config: ConfigFile = {
    schemaFile: 'http://127.0.0.1:8000/openapi.json',
    apiFile: './src/services/mainApi.ts',
    apiImport: 'mainApi',
    outputFiles: FILES,
    hooks: true,
    tag: true,
};

export default config;
