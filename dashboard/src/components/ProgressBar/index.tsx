import React, { useEffect, useRef, useState } from 'react';
import cx from 'classnames';
import { usePrevious } from 'hooks';
import css from './index.module.css';

export interface Props {
    className?: string;
    isActive: boolean | null;
    progress?: number | null;
}

const ProgressBar: React.FC<Props> = ({ className, isActive, progress: globalProgress = null }: Props) => {
    const [progress, setProgress] = useState<number>(0);
    const prevIsActive = usePrevious(isActive);
    const step = useRef(0.01);
    const currentProgress = useRef<number>(0);
    const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);
    const isActiveRef = useRef<boolean>(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        isActiveRef.current = !!isActive;

        if (isActive) {
            setProgress(0);
            step.current = 0.01;
            currentProgress.current = 0;
            startCalculateProgress();
        }

        if (prevIsActive === true && isActive === false) {
            setProgress(100);
            setTimeout(() => setProgress(0), 800);
        }

        if (isActive === null) {
            setProgress(0);
        }

        if (!isActive && timeout.current) {
            clearTimeout(timeout.current);
        }
    }, [isActive]);

    useEffect(() => {
        if (globalProgress !== null) setProgress(globalProgress);
        else {
            setProgress(0);
        }
    }, [globalProgress]);

    const calculateProgress = () => {
        currentProgress.current += step.current;
        const progress = Math.round((Math.atan(currentProgress.current) / (Math.PI / 2)) * 100 * 1000) / 1000;

        setProgress(progress);

        if (progress > 70) step.current = 0.005;

        if (timeout.current && (progress >= 100 || !isActiveRef.current)) clearTimeout(timeout.current);

        if (isActiveRef.current) timeout.current = setTimeout(calculateProgress, 20);
    };

    const startCalculateProgress = () => {
        setTimeout(calculateProgress, 1);
    };

    return (
        <div ref={ref} className={cx(css.bar, className)}>
            <div className={css.progress} style={{ width: `${progress}%` }} />
        </div>
    );
};

export default ProgressBar;
