import {
    variablesToArray,
    variablesToTableString,
    regionsToSelectFieldOptions,
    instanceTypesToSelectFieldOptions,
    isErrorWithMessage,
    arrayToRecordByKeyName,
    compareSimpleObject,
    getRegionByName,
    getDateAgoSting,
    MINUTE,
    getUrlWithOutTrailingSlash,
    getYesterdayTimeStamp,
    getDateFewDaysAgo,
    getFolderNameFromPath,
    getRepoName,
    getRepoTreeUrl,
    formatRepoUrl,
    getUid,
    mibToBytes,
    formatBytes,
    createUrlWithBase,
    maskText,
} from './index';

describe('test libs', () => {
    const data: TVariables = {
        batch_size: '2',
        model: '117M',
        learning_rate: '0.00003',
    };

    test('variables object to array', () => {
        expect(variablesToArray(data)).toEqual([
            { key: 'batch_size', value: '2' },
            { key: 'model', value: '117M' },
            { key: 'learning_rate', value: '0.00003' },
        ]);
    });

    test('variables to string', () => {
        expect(variablesToTableString({})).toBe('');
        expect(variablesToTableString(data)).toBe('batch_size “2” +2');
    });

    test('regions to select field options', () => {
        const mockData: IRegion[] = [
            {
                name: 'eu-north-1',
                title: 'Europe',
                location: 'Stockholm',
            },
            {
                name: 'ap-south-1',
                title: 'Asia Pacific',
                location: 'Mumbai',
            },
        ];

        expect(regionsToSelectFieldOptions()).toEqual([]);
        expect(regionsToSelectFieldOptions([])).toEqual([]);

        expect(regionsToSelectFieldOptions(mockData)).toEqual([
            {
                value: 'eu-north-1',
                title: 'Europe (Stockholm)',
            },
            {
                value: 'ap-south-1',
                title: 'Asia Pacific (Mumbai)',
            },
        ]);
    });

    test('instance types to select field options', () => {
        const mockData: IInstanceType[] = [
            {
                instance_type: 'test',
                purchase_types: [],
            },
            {
                instance_type: 'test1',
                purchase_types: [],
            },
        ];

        expect(instanceTypesToSelectFieldOptions()).toEqual([]);
        expect(instanceTypesToSelectFieldOptions([])).toEqual([]);

        expect(instanceTypesToSelectFieldOptions(mockData)).toEqual([
            {
                value: 'test',
                title: 'test',
            },
            {
                value: 'test1',
                title: 'test1',
            },
        ]);
    });

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

    test('compare simple project', () => {
        expect(compareSimpleObject({ test: 'test' }, { test: 'test' })).toBeTruthy();
        expect(compareSimpleObject({ test: 4 }, { test: 4 })).toBeTruthy();
        expect(compareSimpleObject({ test: 4 }, { test: null })).toBeFalsy();
        expect(compareSimpleObject({ test: undefined }, { test: null })).toBeFalsy();
        expect(compareSimpleObject({ test: 'test', test2: 'test2' }, { test: 'test', test2: 'test2' })).toBeTruthy();
    });

    test('get region by name', () => {
        const regions: IRegion[] = [
            {
                name: 'eu-north-1',
                title: 'Europe',
                location: 'Stockholm',
            },
            {
                name: 'ap-south-1',
                title: 'Asia Pacific',
                location: 'Mumbai',
            },
        ];

        expect(getRegionByName(regions, regions[0].name)).toEqual(regions[0]);
        expect(getRegionByName(regions, regions[1].name)).toEqual(regions[1]);
        expect(getRegionByName(regions, 'test')).toBeUndefined();
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

    test('getYesterdayTimeStamp', () => {
        const date = new Date();
        date.setDate(date.getDate() - 1);
        const yesterdayDate = new Date(getYesterdayTimeStamp());

        expect(yesterdayDate.getDate()).toEqual(date.getDate());
        expect(yesterdayDate.getMonth()).toEqual(date.getMonth());
        expect(yesterdayDate.getFullYear()).toEqual(date.getFullYear());
    });

    test('get date few days ago', () => {
        for (let i = 0; i <= 15; i++) {
            const date = new Date();
            const dateAgo = new Date(getDateFewDaysAgo(i));
            date.setDate(date.getDate() - i);

            expect(dateAgo.getDate()).toEqual(date.getDate());
            expect(dateAgo.getMonth()).toEqual(date.getMonth());
            expect(dateAgo.getFullYear()).toEqual(date.getFullYear());
        }

        const date = new Date(1645437591390);
        const dateAgo = new Date(getDateFewDaysAgo(10, date.getTime()));
        date.setDate(date.getDate() - 10);

        expect(dateAgo.getDate()).toEqual(date.getDate());
        expect(dateAgo.getMonth()).toEqual(date.getMonth());
        expect(dateAgo.getFullYear()).toEqual(date.getFullYear());
    });

    test('getUrlWithOutTrailingSlash', () => {
        expect(getUrlWithOutTrailingSlash('/login/')).toEqual('/login');
        expect(getUrlWithOutTrailingSlash('/')).toEqual('/');
        expect(getUrlWithOutTrailingSlash('/invite/')).toEqual('/invite');
        expect(getUrlWithOutTrailingSlash('/invite')).toEqual('/invite');
    });

    test('get folder name from path', () => {
        expect(getFolderNameFromPath('')).toEqual('');
        expect(getFolderNameFromPath('test')).toEqual('test');
        expect(getFolderNameFromPath('/test/test1')).toEqual('test1');
        expect(getFolderNameFromPath('test/test1/test2/')).toEqual('test2');
        expect(getFolderNameFromPath('/test/test1/test2/test3/')).toEqual('test3');
    });

    test('get repo name', () => {
        const repoUrl = 'https://github.com/dstackai/gpt-2.git';

        expect(getRepoName('')).toBe('');
        expect(getRepoName(repoUrl)).toBe('gpt-2.git');
    });

    test('format repo url', () => {
        expect(formatRepoUrl('https://github.com/dstackai/gpt-2.git')).toBe('https://github.com/dstackai/gpt-2');
        expect(formatRepoUrl('')).toBeNull();
        expect(formatRepoUrl('github.com/dstackai/gpt-2.git')).toBeNull();
    });

    test('get repo commit url', () => {
        expect(getRepoTreeUrl('https://github.com/dstackai/gpt-2.git', '15e74f790736165c3fe1cb103a78f4134053ac83')).toBe(
            'https://github.com/dstackai/gpt-2/tree/15e74f790736165c3fe1cb103a78f4134053ac83',
        );
        expect(getRepoTreeUrl('', '15e74f790736165c3fe1cb103a78f4134053ac83')).toBeNull();
        expect(getRepoTreeUrl('github.com/dstackai/gpt-2.git', '15e74f790736165c3fe1cb103a78f4134053ac83')).toBeNull();
    });

    test('get unique id', () => {
        const set = new Set();
        const iterationCount = 20;

        for (let i = 0; i < iterationCount; i++) set.add(getUid());

        expect(set.size).toBe(iterationCount);
    });

    test('MiB to Bytes', () => {
        expect(mibToBytes(16384)).toBe(17179869184);
    });

    test('Format bytes', () => {
        expect(formatBytes(0)).toBe('0Bytes');
        expect(formatBytes(1073741824)).toBe('1GB');
        expect(formatBytes(mibToBytes(16384))).toBe('16GB');
    });

    test('Create url path with base path', () => {
        expect(createUrlWithBase('/', '/test')).toBe('/test');
        expect(createUrlWithBase('/', 'test/test')).toBe('/test/test');
        expect(createUrlWithBase('', '/test/test')).toBe('/test/test');
        expect(createUrlWithBase('https://test.ru', '/test')).toBe('https://test.ru/test');
        expect(createUrlWithBase('https://test.ru/', '/test/test')).toBe('https://test.ru/test/test');
    });

    test('Mask text', () => {
        expect(maskText('')).toBe('');
        expect(maskText('test')).toBe('****');
        expect(maskText('test2')).toBe('*****');
    });
});
