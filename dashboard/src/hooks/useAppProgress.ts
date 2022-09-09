import useAppDispatch from './useAppDispatch';
import useAppSelector from './useAppSelector';
import { completeAppProgress, selectAppProgress, startAppProgress, stopAppProgress } from 'App/slice';
import { useEffect } from 'react';

function useAppProgress(active?: boolean) {
    const { isActive, state } = useAppSelector(selectAppProgress);
    const dispatch = useAppDispatch();

    const start = () => {
        dispatch(startAppProgress());
    };

    const complete = () => {
        dispatch(completeAppProgress());
    };

    const stop = () => {
        dispatch(stopAppProgress());
    };

    useEffect(() => {
        return () => stop();
    }, []);

    useEffect(() => {
        if (typeof active === 'boolean') {
            if (active) start();
            else complete();
        }
    }, [active]);

    return {
        start,
        complete,
        stop,
        isActive,
        progress: state,
    };
}

export default useAppProgress;
