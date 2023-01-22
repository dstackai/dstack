import { useState } from 'react';

export default function useLocalStorageState<T>(value: T, key: string): [value: T, set: (value: T) => void] {
    const [stateValue, setState] = useState<T>(() => {
        const storageValue = localStorage.getItem(key);

        if (storageValue) return JSON.parse(storageValue) as T;

        return value;
    });

    const set = (newVal: T) => {
        setState(newVal);
        localStorage.setItem(key, JSON.stringify(newVal));
    };

    return [stateValue, set];
}
