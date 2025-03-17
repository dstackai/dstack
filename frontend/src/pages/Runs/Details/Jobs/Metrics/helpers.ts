import { GByte, kByte, MByte } from './consts';

export const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: 'numeric',
        hour12: !1,
    });
};

export const formatPercent = (percent: number) => `${percent} %`;

export const bytesFormatter = (bytes: number, hasPostfix = true) => {
    if (bytes >= GByte) {
        return (bytes / GByte).toFixed(1) + (hasPostfix ? ' GB' : '');
    }

    if (bytes >= MByte) {
        return (bytes / MByte).toFixed(1) + (hasPostfix ? ' MB' : '');
    }

    if (bytes >= kByte) {
        return (bytes / kByte).toFixed(1) + (hasPostfix ? ' KB' : '');
    }

    return bytes + (hasPostfix ? ' B' : '');
};
