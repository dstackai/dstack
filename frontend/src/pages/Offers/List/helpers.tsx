import React from 'react';

import { RequestParam } from '../../../libs/filters';

import styles from './styles.module.scss';

const rangeSeparator = '..';

export function convertMiBToGB(mib: number) {
    return mib / 1024;
}

export const getPropertyFilterOptions = (gpus: IGpu[]) => {
    const names = new Set<string>();
    const backends = new Set<string>();
    const counts = new Set<string>();

    gpus.forEach((gp) => {
        names.add(gp.name);

        if (gp.backend) {
            backends.add(gp.backend);
        }

        if (gp.backends?.length) {
            gp.backends.forEach((i) => backends.add(i));
        }

        const countRange = renderRange(gp.count);

        if (gp.count && countRange) {
            counts.add(countRange);
        }
    });

    return {
        names,
        backends,
        counts,
    };
};

export const round = (number: number) => Math.round(number * 100) / 100;

export const renderRange = (range: { min?: number; max?: number }) => {
    if (typeof range.min === 'number' && typeof range.max === 'number' && range.max != range.min) {
        return `${round(range.min)}${rangeSeparator}${round(range.max)}`;
    }

    return range.min?.toString() ?? range.max?.toString();
};

export const renderRangeJSX = (range: { min?: number; max?: number }) => {
    if (typeof range.min === 'number' && typeof range.max === 'number' && range.max != range.min) {
        return (
            <>
                {round(range.min)}
                <span className={styles.greyText}>{rangeSeparator}</span>
                {round(range.max)}
            </>
        );
    }

    return range.min?.toString() ?? range.max?.toString();
};

export const rangeToObject = (
    range: RequestParam,
    {
        requireUnit = false,
    }: {
        requireUnit?: boolean;
    } = {},
): { min?: number; max?: number } | undefined => {
    const hasGbUnit = (value?: string) => /gb/i.test(value ?? '');

    if (!range) return;

    if (typeof range === 'string') {
        const [minString, maxString] = range.split(rangeSeparator);
        const normalizeNumericPart = (value?: string) => (value ?? '').replace(/[^\d.]/g, '');
        const parseBound = (value?: string): number | undefined => {
            if (requireUnit && value && !hasGbUnit(value)) {
                return undefined;
            }
            const normalized = normalizeNumericPart(value);
            if (!normalized) {
                return undefined;
            }
            const parsed = Number(normalized);
            return isNaN(parsed) ? undefined : parsed;
        };

        const min = parseBound(minString);
        const max = parseBound(maxString);

        if (typeof min === 'number' && typeof max === 'number') {
            return { min, max };
        }

        if (typeof min === 'number') {
            return { min };
        }

        if (typeof max === 'number') {
            return { max };
        }
    }

    if (typeof range === 'number') {
        return requireUnit ? undefined : { min: range, max: range };
    }

    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-expect-error
    return range;
};
