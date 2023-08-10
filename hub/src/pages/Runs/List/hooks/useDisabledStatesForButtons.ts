import { useMemo } from 'react';

import { isAvailableAbortingForRun, isAvailableDeletingForRun, isAvailableStoppingForRun } from '../../utils';

type hookArgs = {
    selectedRuns?: readonly IRunListItem[] | IRunListItem[];
    isStopping?: boolean;
    isAborting?: boolean;
    isDeleting?: boolean;
};
export const useDisabledStatesForButtons = ({ selectedRuns, isStopping, isAborting, isDeleting }: hookArgs) => {
    const isRunningOperation = Boolean(isStopping || isAborting || isDeleting);

    const isDisabledAbortButton = useMemo<boolean>(() => {
        return (
            !selectedRuns?.length ||
            selectedRuns.some((item) => !isAvailableAbortingForRun(item.run_head.status)) ||
            isRunningOperation
        );
    }, [selectedRuns, isRunningOperation]);

    const isDisabledStopButton = useMemo<boolean>(() => {
        return (
            !selectedRuns?.length ||
            selectedRuns.some((item) => !isAvailableStoppingForRun(item.run_head.status)) ||
            isRunningOperation
        );
    }, [selectedRuns, isRunningOperation]);

    const isDisabledDeleteButton = useMemo<boolean>(() => {
        return (
            !selectedRuns?.length ||
            selectedRuns.some((item) => !isAvailableDeletingForRun(item.run_head.status)) ||
            isRunningOperation
        );
    }, [selectedRuns, isRunningOperation]);

    return { isDisabledAbortButton, isDisabledStopButton, isDisabledDeleteButton } as const;
};
