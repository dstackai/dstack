import { useCallback, useEffect, useState } from 'react';

export const useLocalStorageState = <T>(key: string, defaultState?: T): [T, (state: T) => void] => {
    const storageItem = localStorage.getItem(key);
    const [state, setState] = useState(storageItem ? JSON.parse(storageItem) : defaultState);

    useEffect(() => {
        const listener = (event: StorageEvent) => {
            if (event.key === key) {
                setState(event.newValue ? JSON.parse(event.newValue) : defaultState);
            }
        };

        window.addEventListener('storage', listener);

        return () => {
            window.removeEventListener('storage', listener);
        };
    }, [key, defaultState]);

    const setStorage = useCallback(
        (newState: T) => {
            const storageState = JSON.stringify(newState);

            window.dispatchEvent(
                new StorageEvent('storage', {
                    key,
                    newValue: storageState,
                }),
            );
            localStorage.setItem(key, storageState);
        },
        [key],
    );

    return [state, setStorage];
};
