import React from 'react';

export { default as isErrorWithMessage, isErrorWithError } from './isErrorWithMessage';
import { formatDistanceToNowStrict, format } from 'date-fns';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function arrayToRecordByKeyName<T extends { [K in keyof T]: any }, K extends keyof T>(array: T[], selector: K) {
    return array.reduce((acc, item) => {
        acc[item[selector]] = item;
        return acc;
    }, {} as Record<T[K], T>);
}

export function wait(delayInMS: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, delayInMS));
}

export function variablesToArray(variables: TVariables): IVariable[] {
    return Object.keys(variables).reduce((result, key) => {
        result.push({ key: key, value: variables[key] });

        return result;
    }, [] as IVariable[]);
}

export function variablesToTableString(variables: TVariables): string {
    const variablesArray = variablesToArray(variables);

    if (!variablesArray.length) return '';

    const moreCount = variablesArray.length - 1;

    return `${variablesArray[0].key} “${variablesArray[0].value}” ${moreCount ? `+${moreCount}` : ''}`;
}

export function regionsToSelectFieldOptions(regions?: IRegion[]): SelectOption[] {
    if (!regions) return [];

    return regions.map((r) => ({ value: r.name, title: `${r.title} (${r.location})` } as SelectOption));
}

export function instanceTypesToSelectFieldOptions(instanceType?: IInstanceType[]): SelectOption[] {
    if (!instanceType) return [];

    return instanceType.map((it) => ({ value: it.instance_type, title: it.instance_type } as SelectOption));
}

export function goToUrl(url: string, blank?: boolean): void {
    const link = document.createElement('a');
    link.style.opacity = '0';
    link.style.position = 'absolute';
    link.style.top = '-2000px';

    if (blank) link.target = '_blank';

    link.href = url;

    document.body.append(link);
    link.click();
    link.remove();
}

export const copyToClipboard = (copyText: string, success?: () => void, failed?: () => void) => {
    navigator.clipboard.writeText(copyText).then(success, failed);
};

type simpleObject = { [key: string]: string | number | null | undefined };

export const compareSimpleObject = (object: simpleObject, twoObject: simpleObject): boolean => {
    return JSON.stringify(object) === JSON.stringify(twoObject);
};

export const getRegionByName = (regions: IRegion[], name: string): IRegion | undefined => {
    return regions.find((r) => r.name === name);
};

export const MINUTE = 60000;

export const getDateAgoSting = (time: number): string => {
    try {
        if (Date.now() - time < MINUTE) return 'Just now';

        if (Date.now() - time < MINUTE * 60 * 24) return formatDistanceToNowStrict(new Date(time), { addSuffix: true });

        return format(new Date(time), 'dd/MM/yyyy');
    } catch (err) {
        return '';
    }
};

export const getUrlWithOutTrailingSlash = (url: string): string => {
    if (url === '/') return url;

    return url.replace(/\/$/, '');
};

export const getDateFewDaysAgo = (daysAgo: number, timestamp: number = new Date().getTime()) => {
    const date = new Date(timestamp);
    date.setDate(date.getDate() - daysAgo);
    return date.getTime();
};

export const getYesterdayTimeStamp = () => {
    return getDateFewDaysAgo(1);
};

export const getFolderNameFromPath = (path: string): string => {
    const folders = path.replace(/^\//, '').replace(/\/$/, '').split('/');

    return folders.pop() ?? '';
};

export const getRepoName = (repoUrl: string): string => {
    const name = repoUrl.split('/').pop();

    if (!name) return '';

    return name;
};

export const formatRepoUrl = (repoUrl: string): string | null => {
    const repoWithoutExtension = repoUrl.replace(/\.\w+$/, '');
    if (!/^https?:\/\//.test(repoWithoutExtension)) return null;

    return repoWithoutExtension;
};

export const getRepoTreeUrl = (repoUrl: string, hash: string): string | null => {
    const normalizedRepoUrl = formatRepoUrl(repoUrl);

    if (!normalizedRepoUrl) return null;

    return `${normalizedRepoUrl}/tree/${hash}`;
};

export const getUid = (a?: string): string => {
    return a ? (0 | (Math.random() * 16)).toString(16) : ('' + 1e11 + 1e11).replace(/1|0/g, getUid);
};

export const mibToBytes = (value: number) => value * 1048576;

export const formatBytes = (bytes: number, decimals = 2): string => {
    if (bytes === 0) return '0Bytes';

    const k = 1024;

    const dm = decimals <= 0 ? 0 : decimals;

    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];

    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + sizes[i];
};

export const createUrlWithBase = (base: string, urlPath: string): string => {
    if (/\/$/.test(base) && /^\//.test(urlPath)) urlPath = urlPath.replace(/^\//, '');

    return base + urlPath;
};

export const maskText = (text: string): string => {
    if (!text.length) return '';

    return new Array(text.length).fill('*').join('');
};

export const stopPropagation = (event: MouseEvent | TouchEvent | React.MouseEvent<HTMLElement, MouseEvent>) => {
    event.preventDefault();
    event.stopPropagation();
};
