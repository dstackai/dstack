import { awsLogEventToString, awsQueryResulToString } from './aws';

describe('Clouds Libs', () => {
    test('aws log event convert  to string', () => {
        const event: IAWSEvent = {
            eventId: '36686662880149846238674172635973980087248812964533698560',
            ingestionTime: 1645086859413,
            logStreamName: 'fbcc4a38033a',
            message: '{"log":"Collecting fire\\u003e=0.1.3","source":"stdout"}',
            timestamp: 1645086859365,
        };

        expect(awsLogEventToString({ ...event, message: '' })).toBe('');
        expect(awsLogEventToString(event)).toBe('2022-02-17 11:34 Collecting fire>=0.1.3');
    });

    test('aws query result to string', () => {
        const resultItem: TAWSQueryResultItem = [
            {
                field: '@logStream',
                value: 'fbcc4a38033a',
            },
            {
                field: '@timestamp',
                value: '2022-02-17 14:53:53.531',
            },
            {
                field: 'log',
                value: '[4750 | 22743.42] loss=0.03 avg=0.05',
            },
            {
                field: '@ptr',
                value: 'Cl4KJQohMTQyNDIxNTkwMDY2Om9sZ2Vubi90YW1lLWVhcndpZy0xEAISNRoYAgYWqLmoAAAAAYwVMFMABiDmESAAAACCIAEomO+uwfAvMPvDs8HwLzgCQL4BSKsIUJkEEAEYAQ==',
            },
        ];

        expect(awsQueryResulToString(resultItem)).toBe('2022-02-17 14:53 [4750 | 22743.42] loss=0.03 avg=0.05');
    });
});
