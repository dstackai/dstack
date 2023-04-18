import { arrayToRecordByKeyName, getDateAgoSting, getUid, isErrorWithMessage, MINUTE } from './index';

describe('test libs', () => {
    test('Check is error with message', () => {
        expect(isErrorWithMessage({})).toBeFalsy();
        expect(isErrorWithMessage(null)).toBeFalsy();
        expect(isErrorWithMessage({ data: { test: 'test' } })).toBeFalsy();
        expect(isErrorWithMessage({ data: { message: 'error message' } })).toBeTruthy();
    });

    test('array to record by name', () => {
        const mockData = [
            { name: 'test', lastname: 'test_lastname' },
            { name: 'test2', lastname: 'test_lastname2' },
        ];

        expect(arrayToRecordByKeyName(mockData, 'name')).toEqual({
            test: mockData[0],
            test2: mockData[1],
        });

        expect(arrayToRecordByKeyName(mockData, 'lastname')).toEqual({
            test_lastname: mockData[0],
            test_lastname2: mockData[1],
        });
    });

    test('getDateAgoSting', () => {
        const date = new Date();
        const timestamp = date.getTime();
        date.setDate(date.getDate() - 1);
        const day: string = date.getDate() < 10 ? `0${date.getDate()}` : `${date.getDate()}`;
        const month: string = date.getMonth() < 9 ? `0${date.getMonth() + 1}` : `${date.getMonth() + 1}`;
        const year: string = date.getFullYear().toString();

        expect(getDateAgoSting(timestamp)).toEqual('Just now');
        expect(getDateAgoSting(timestamp - MINUTE + 100)).toEqual('Just now');
        expect(getDateAgoSting(timestamp - MINUTE)).toEqual('1 minute ago');
        expect(getDateAgoSting(timestamp - MINUTE * 2)).toEqual('2 minutes ago');
        expect(getDateAgoSting(timestamp - MINUTE * 60)).toEqual('1 hour ago');
        expect(getDateAgoSting(timestamp - MINUTE * 60 * 2)).toEqual('2 hours ago');
        expect(getDateAgoSting(timestamp - MINUTE * 60 * 24)).toEqual(`${day}/${month}/${year}`);
    });

    test('get unique id', () => {
        const set = new Set();
        const iterationCount = 20;

        for (let i = 0; i < iterationCount; i++) set.add(getUid());

        expect(set.size).toBe(iterationCount);
    });
});
