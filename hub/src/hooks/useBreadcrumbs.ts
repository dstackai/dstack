import { useEffect } from 'react';

import { setBreadcrumb } from 'App/slice';

import useAppDispatch from './useAppDispatch';

export const useBreadcrumbs = (breadcrumbs: TBreadcrumb[]) => {
    const dispatch = useAppDispatch();

    useEffect(() => {
        dispatch(setBreadcrumb(breadcrumbs));

        return () => {
            dispatch(setBreadcrumb(null));
        };
    }, [breadcrumbs]);
};
