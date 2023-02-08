import React from 'react';

export { default as isErrorWithMessage, isErrorWithError } from './isErrorWithMessage';
import { formatDistanceToNowStrict, format } from 'date-fns';
export * from './isValidToken';

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

export const getDateFewDaysAgo = (daysAgo: number, timestamp: number = new Date().getTime()) => {
    const date = new Date(timestamp);
    date.setDate(date.getDate() - daysAgo);
    return date.getTime();
};

export const getYesterdayTimeStamp = () => {
    return getDateFewDaysAgo(1);
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

export const maskText = (text: string): string => {
    if (!text.length) return '';

    return new Array(text.length).fill('*').join('');
};

export const stopPropagation = (event: MouseEvent | TouchEvent | React.MouseEvent<HTMLElement, MouseEvent>) => {
    event.preventDefault();
    event.stopPropagation();
};

export const buildRoute = (route: string, params: HashMap): string => {
    return Object.keys(params).reduce((acc, key) => {
        const regExp = new RegExp(`:${key}`);

        return acc.replace(regExp, params[key] as string);
    }, route);
};
