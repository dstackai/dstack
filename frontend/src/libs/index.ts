export {
    default as isErrorWithMessage,
    isResponseServerFormFieldError,
    isResponseServerError,
    getServerError,
} from './serverErrors';
import { format, formatDistanceToNowStrict } from 'date-fns';

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

export const getUid = (a?: string): string => {
    return a ? (0 | (Math.random() * 16)).toString(16) : ('' + 1e11 + 1e11).replace(/1|0/g, getUid);
};

export const buildRoute = (route: string, params: HashMap): string => {
    return Object.keys(params).reduce((acc, key) => {
        const regExp = new RegExp(`:${key}`);

        return acc.replace(regExp, params[key] as string);
    }, route);
};

export const formatBytes = (bytes: number, decimals = 2): string => {
    if (bytes === 0) return '0Bytes';

    const k = 1024;

    const dm = decimals <= 0 ? 0 : decimals;

    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];

    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + sizes[i];
};

export const centsToFormattedString = (cents: number, currency?: string): string => {
    const floatValue = cents / 100;

    return `${floatValue < 0 ? '-' : ''}${currency}${Math.abs(floatValue).toFixed(2)}`;
};

export const riseRouterException = (status = 404, json = 'Not Found'): never => {
    // eslint-disable-next-line @typescript-eslint/no-throw-literal
    throw new Response(json, { status });
};

export const base64ToArrayBuffer = (base64: string) => {
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes;
};

export const isValidUrl = (urlString: string) => {
    try {
        return Boolean(new URL(urlString));
    } catch (e) {
        return false;
    }
};

export const includeSubString = (value: string, query: string) => {
    return value.toLowerCase().includes(query.trim().toLowerCase());
};
