import { getRequirementsString } from './job';

describe('Test Job libs', () => {
    test('Get Requirements string', () => {
        const mocks: {
            data: IJobRequirements;
            result: string;
        }[] = [
            {
                data: {
                    cpu: {
                        count: 4,
                    },
                    memory: 16384,
                    gpu: {
                        name: null,
                        count: 1,
                        memory: null,
                    },
                },

                result: 'CPU 4, 16GB',
            },
            {
                data: {
                    cpu: {
                        count: 4,
                    },
                    memory: 16384,
                    gpu: {
                        name: 'v100',
                        count: 1,
                        memory: 16384,
                    },
                },

                result: 'CPU 4, 16GB, GPU v100',
            },
            {
                data: {
                    cpu: {
                        count: 4,
                    },
                    memory: 16384,
                    gpu: {
                        name: 'v100',
                        count: 2,
                        memory: 16384,
                    },
                },

                result: 'CPU 4, 16GB, GPU v100x2',
            },
        ];

        mocks.forEach((mock) => {
            expect(getRequirementsString(mock.data)).toBe(mock.result);
        });
    });
});
