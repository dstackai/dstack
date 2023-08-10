import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { useStopRunsMutation } from 'services/run';

import { getGroupedRunsByProjectAndRepoID } from '../helpers';

export const useStopRuns = (isAborting?: boolean) => {
    const { t } = useTranslation();
    const [stopRun, { isLoading: isStopping }] = useStopRunsMutation();
    const [pushNotification] = useNotifications();

    const stopRuns = useCallback(
        (runs: IRunListItem[]) => {
            const groupedRuns = getGroupedRunsByProjectAndRepoID(runs);

            const request = Promise.all(
                Object.keys(groupedRuns).map((key) => {
                    const runsGroup = groupedRuns[key];

                    return stopRun({
                        name: runsGroup[0].project,
                        repo_id: runsGroup[0]?.repo_id ?? undefined,
                        run_names: runsGroup.map((item) => item.run_head.run_name),
                        abort: !!isAborting,
                    }).unwrap();
                }),
            );

            request.catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });

            return request;
        },
        [isAborting],
    );

    return { stopRuns, isStopping } as const;
};

export const useAbortRuns = () => {
    const { stopRuns: abortRuns, isStopping: isAborting } = useStopRuns(true);

    return { abortRuns, isAborting } as const;
};
