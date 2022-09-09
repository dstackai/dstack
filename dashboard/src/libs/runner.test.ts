import { getResourcesString } from 'libs/runner';

describe('Test Runner libs', () => {
    test('Get resources string', () => {
        const mocks: {
            data: IRunnerResources;
            result: string;
        }[] = [
            {
                data: {
                    cpu: {
                        count: 4,
                    },
                    memory_mib: 16384,
                    gpus: [],
                },

                result: 'CPU 4, 16GB',
            },
            {
                data: {
                    cpu: {
                        count: 4,
                    },
                    memory_mib: 16384,
                    gpus: [
                        {
                            name: 'v100',
                            memory_mib: 16384,
                        },
                    ],
                },

                result: 'CPU 4, 16GB, GPU v100',
            },
            {
                data: {
                    cpu: {
                        count: 4,
                    },
                    memory_mib: 16384,
                    gpus: [
                        {
                            name: 'v100',
                            memory_mib: 16384,
                        },
                        {
                            name: 'v100',
                            memory_mib: 16384,
                        },
                    ],
                },

                result: 'CPU 4, 16GB, GPU v100x2',
            },
        ];

        mocks.forEach((mock) => {
            expect(getResourcesString(mock.data)).toBe(mock.result);
        });
    });
});
