import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { useStopRunsMutation } from 'services/run';

import { getGroupedRunsByProjectAndRepoID } from '../helpers';

export const useStopRuns = (isAborting?: boolean) => {
    const { t } = useTranslation();
    const [stopRun, { isLoading: isStopping }] = useStopRunsMutation();
    const [pushNotification] = useNotifications();

    const stopRuns = useCallback(
        (runs: IRun[]) => {
            const groupedRuns = getGroupedRunsByProjectAndRepoID(runs);

            const request = Promise.all(
                Object.keys(groupedRuns).map((key) => {
                    const runsGroup = groupedRuns[key];

                    return stopRun({
                        project_name: runsGroup[0].project_name,
                        runs_names: runsGroup.map((item) => item.run_spec.run_name),
                        abort: !!isAborting,
                    }).unwrap();
                }),
            );

            request.catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
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
