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

export const rangeToObject = (range: RequestParam): { min?: number; max?: number } | undefined => {
    if (!range) return;

    if (typeof range === 'string') {
        const [minString, maxString] = range.split(rangeSeparator);

        const min = Number(minString);
        const max = Number(maxString);

        if (!isNaN(min) && !isNaN(max)) {
            return { min, max };
        }

        if (!isNaN(min)) {
            return { min, max: min };
        }

        if (!isNaN(max)) {
            return { min: max, max };
        }
    }

    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-expect-error
    return range;
};
