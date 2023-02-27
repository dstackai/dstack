import useAppDispatch from './useAppDispatch';
import { setBreadcrumb } from 'App/slice';
import { useEffect } from 'react';

export const useBreadcrumbs = (breadcrumbs: TBreadcrumb[]) => {
    const dispatch = useAppDispatch();

    useEffect(() => {
        dispatch(setBreadcrumb(breadcrumbs));

        return () => {
            dispatch(setBreadcrumb(null));
        };
    }, [breadcrumbs]);
};
