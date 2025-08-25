const rangeSeparator = '..';

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

const round = (number: number) => Math.round(number * 100) / 100;

export const renderRange = (range: { min?: number; max?: number }) => {
    if (typeof range.min === 'number' && typeof range.max === 'number' && range.max != range.min) {
        return `${round(range.min)}${rangeSeparator}${round(range.max)}`;
    }

    return range.min?.toString() ?? range.max?.toString();
};

export const stringRangeToObject = (rangeString: string): { min?: number; max?: number } | undefined => {
    if (!rangeString) return;

    const [minString, maxString] = rangeString.split(rangeSeparator);

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
};
