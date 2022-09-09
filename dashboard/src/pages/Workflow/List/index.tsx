import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import Switcher from 'components/Switcher';
import EmptyMessage from 'components/EmptyMessage';
import { isFinished } from 'libs/run';
import { useGetWorkflowsQuery } from 'services/workflows';
import { POLLING_INTERVAL, STORAGE_KEYS } from 'consts';
import { URL_PARAMS } from 'route/url-params';
import { getRouterModule, RouterModules } from 'route';
import { useAppProgress, useLocalStorageState } from 'hooks';
import RunCard from './components/RunCard';
import css from './index.module.css';

const LAST_RUNS_COUNT = 50;

const RunsList: React.FC = () => {
    const { t } = useTranslation();
    const [isShowAllRuns, setIsShowAllRuns] = useLocalStorageState<boolean>(false, STORAGE_KEYS.ALL_RUNS_LIST_FILTER);
    const urlParams = useParams();
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);

    const { data, isLoading, isFetching } = useGetWorkflowsQuery(
        {
            count: LAST_RUNS_COUNT,
            userName: urlParams[URL_PARAMS.USER_NAME],
            repoUserName: urlParams[URL_PARAMS.REPO_USER_NAME],
            repoName: urlParams[URL_PARAMS.REPO_NAME],
        },
        { pollingInterval: POLLING_INTERVAL },
    );

    useAppProgress(isFetching);

    const filteredData = useMemo<typeof data>(() => {
        if (!Array.isArray(data)) return data;

        if (isShowAllRuns) return data;

        return data.filter((workflow) => {
            let result = true;

            if (!isShowAllRuns) result = result && !isFinished(workflow);

            return result;
        });
    }, [isShowAllRuns, data]);

    const getWorkflowLink = useCallback(
        (w: IRunWorkflow): string => {
            const pathName = [
                'app',
                urlParams[URL_PARAMS.REPO_USER_NAME] ? 'user-repouser-repo' : 'user-repo',
                w.workflow_name ? 'workflow' : 'run',
            ]
                .filter(Boolean)
                .join('.');

            return newRouter.buildUrl(pathName, {
                [URL_PARAMS.WORKFLOW_NAME]: w.workflow_name,
                [URL_PARAMS.RUN_NAME]: w.run_name,
                [URL_PARAMS.USER_NAME]: urlParams[URL_PARAMS.USER_NAME],
                [URL_PARAMS.REPO_USER_NAME]: urlParams[URL_PARAMS.REPO_USER_NAME],
                [URL_PARAMS.REPO_NAME]: urlParams[URL_PARAMS.REPO_NAME],
            });
        },
        [urlParams],
    );

    return (
        <section className={css.section}>
            <div className={css.filter}>
                {!isLoading && !!data?.length && (
                    <label className={css.switcherLabel}>
                        <Switcher
                            className={css.switcher}
                            checked={isShowAllRuns}
                            onChange={(event) => setIsShowAllRuns(event.currentTarget.checked)}
                        />

                        <span>{t('all_runs')}</span>
                    </label>
                )}
            </div>

            {isLoading && (
                <div className={css.grid}>
                    <div className="skeleton-element" />
                    <div className="skeleton-element" />
                    <div className="skeleton-element" />
                    <div className="skeleton-element" />
                </div>
            )}

            {!isLoading && (!data || !data.length) && (
                <EmptyMessage title={`👀 ${t('no_runs_here')}`} description={t('to_start_your_first_run')} />
            )}

            {!isLoading && data && !!data.length && (
                <div className={css.grid}>
                    {filteredData &&
                        filteredData.map((row, index) => <RunCard to={getWorkflowLink(row)} key={index} item={row} />)}
                </div>
            )}
        </section>
    );
};

export default RunsList;
