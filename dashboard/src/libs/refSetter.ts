import React from 'react';

/**
 * Useful when passing refs from outside, but want to handle internal ref.
 * Keeps passed refs in sync, by creating ref callback
 * @param refs
 */
export function refSetter<T extends HTMLElement | null>(...refs: React.ForwardedRef<T>[]): (instance: T | null) => void {
    return (ref) => {
        refs.forEach((someRef) => {
            if (!someRef) return;
            if (typeof someRef === 'function') {
                someRef(ref);
            } else {
                someRef.current = ref;
            }
        });
    };
}
